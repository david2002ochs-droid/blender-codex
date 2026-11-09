"""Plugin-owned durable index/snapshots, separate from all Codex configuration.

Only register() on an observed plugin-created thread grants ownership. Opening
never enumerates app-server/CLI history or accepts a path supplied by a browser.
"""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time

_HANDLE = re.compile(r"[0-9a-f]{48}\Z")


class ChatHistory:
    MAX_SNAPSHOT = 8 * 1024 * 1024

    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "index.sqlite3"
        with self._connection() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS threads (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL, project TEXT NOT NULL)")

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database, timeout=3)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def threads(self):
        with self._connection() as connection:
            return [dict(zip(("id", "title", "created_at", "updated_at", "project"), row)) for row in connection.execute(
                "SELECT id,title,created_at,updated_at,project FROM threads ORDER BY updated_at DESC,id")]

    def owned(self, thread_id):
        if not isinstance(thread_id, str) or not thread_id or len(thread_id) > 256:
            return False
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM threads WHERE id=?", (thread_id,)).fetchone() is not None

    def require(self, thread_id):
        if not self.owned(thread_id):
            raise ValueError("This chat was not created by the Blender plugin or is no longer indexed.")
        return thread_id

    def register(self, thread_id, project="", title="New chat"):
        if not isinstance(thread_id, str) or not thread_id or len(thread_id) > 256:
            raise ValueError("Invalid observed Codex thread ID.")
        now = time.time()
        with self._connection() as connection:
            connection.execute("INSERT OR IGNORE INTO threads VALUES (?,?,?,?,?)", (thread_id, title[:200], now, now, str(project)))

    def rename(self, thread_id, title):
        self.require(thread_id)
        if not isinstance(title, str) or not title.strip() or len(title) > 200 or any(ord(c) < 32 for c in title):
            raise ValueError("Use a chat name of 1–200 characters without control characters.")
        with self._connection() as connection:
            connection.execute("UPDATE threads SET title=?, updated_at=? WHERE id=?", (title.strip(), time.time(), thread_id))

    def title(self, thread_id):
        self.require(thread_id)
        with self._connection() as connection:
            return connection.execute("SELECT title FROM threads WHERE id=?", (thread_id,)).fetchone()[0]

    def _folder(self, thread_id):
        self.require(thread_id)
        folder = (self.directory / hashlib.sha256(thread_id.encode()).hexdigest()).resolve()
        if not folder.is_relative_to(self.directory):
            raise ValueError("History directory is outside the plugin store.")
        return folder

    @staticmethod
    def _atomic(path, data):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".history-", delete=False) as file:
                temporary = Path(file.name)
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save(self, thread_id, projection, resources):
        folder = self._folder(thread_id)
        folder.mkdir(exist_ok=True)
        resource_dir = folder / "resources"
        resource_dir.mkdir(exist_ok=True)
        records = []
        for descriptor, data in resources:
            handle = descriptor.get("id")
            if not isinstance(handle, str) or not _HANDLE.fullmatch(handle) or len(data) > 8 * 1024 * 1024:
                raise ValueError("Invalid history resource.")
            record = dict(descriptor, sha256=hashlib.sha256(data).hexdigest())
            destination = resource_dir / handle
            if not destination.exists():
                self._atomic(destination, data)
            records.append(record)
        snapshot = {"version": 1, "thread_id": thread_id, "projection": projection, "resources": records}
        encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > self.MAX_SNAPSHOT:
            raise ValueError("Chat snapshot exceeds the 8 MiB history limit; authoritative Codex history remains available.")
        self._atomic(folder / "snapshot.json", encoded)
        with self._connection() as connection:
            connection.execute("UPDATE threads SET updated_at=? WHERE id=?", (time.time(), thread_id))

    def load(self, thread_id):
        folder = self._folder(thread_id)
        snapshot_path = folder / "snapshot.json"
        if not snapshot_path.exists():
            return {}, [], []
        with snapshot_path.open("rb") as file:
            raw = file.read(self.MAX_SNAPSHOT + 1)
        if len(raw) > self.MAX_SNAPSHOT:
            raise ValueError("Stored chat snapshot exceeds the history size limit.")
        snapshot = json.loads(raw)
        if snapshot.get("version") != 1 or snapshot.get("thread_id") != thread_id or not isinstance(snapshot.get("projection"), dict):
            raise ValueError("Stored chat snapshot has an unsupported version or identity.")
        entries, missing = [], []
        for descriptor in snapshot.get("resources", []):
            handle = descriptor.get("id")
            if not isinstance(handle, str) or not _HANDLE.fullmatch(handle):
                continue
            path = (folder / "resources" / handle).resolve()
            try:
                if not path.is_relative_to(folder) or path.stat().st_size > 8 * 1024 * 1024:
                    raise ValueError()
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != descriptor.get("sha256"):
                    raise ValueError()
                entries.append((descriptor, data))
            except (OSError, ValueError):
                missing.append(handle)
        return snapshot["projection"], entries, missing
