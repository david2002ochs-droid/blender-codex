"""App-server dynamic function tools; no MCP transport or Blender worker access."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

if __package__:
    from . import hi3d_tool
    from .hi3d_config import load_credentials
else:
    import importlib.util
    # Standalone transport tests must not import the bpy package entrypoint.
    directory = str(Path(__file__).parent)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    import hi3d_tool
    from hi3d_config import load_credentials


class NativeTools:
    TIMEOUT = 1200

    def __init__(self, directory, credentials=None, cwd=None, python=None, env_file=None):
        self.directory = Path(directory).resolve()
        self.credentials = tuple(credentials) if credentials is not None else None
        self.env_file = env_file
        self.cwd = str(Path(cwd or Path.cwd()).resolve())
        self.python = python or self._python()
        self._lock = threading.Lock()

    @staticmethod
    def _python():
        if Path(sys.executable).stem.lower() not in ("blender", "blender-launcher"):
            return sys.executable
        candidates = [Path(sys.prefix) / "bin" / "python.exe", Path(sys.prefix) / "bin" / "python3"]
        candidates += sorted((Path(sys.prefix) / "bin").glob("python3.*"))
        return str(next((p for p in candidates if p.is_file()), candidates[0]))

    @property
    def specs(self):
        return [copy.deepcopy(hi3d_tool.SPEC)]

    def call(self, name, arguments, cancel):
        if name not in (hi3d_tool.NAME, hi3d_tool.LEGACY_NAME):
            return {"success": False, "stage": "input", "error": "Unknown native tool."}
        try:
            arguments = hi3d_tool.validate(arguments)
        except (ValueError, TypeError) as exc:
            return {"success": False, "stage": "input", "error": str(exc)}
        if not self._lock.acquire(blocking=False):
            return {"success": False, "stage": "input", "error": "A Hi3D call is still running. Wait for its result."}
        proc = None
        record = self.directory / "jobs" / (uuid.uuid4().hex + ".json")
        payload = {"arguments": arguments, "cwd": self.cwd,
                   "output_dir": str(self.directory / "models"), "record_path": str(record)}
        try:
            if cancel.is_set():
                return self._interrupted(record, arguments, cancelled=True)
            try:
                payload["credentials"] = load_credentials(explicit=self.credentials, cwd=self.cwd, env_file=self.env_file)
            except ValueError as exc:
                return {"success": False, "stage": "config", "error": str(exc)}
            self.directory.mkdir(parents=True, exist_ok=True)
            options = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL,
                       "cwd": self.cwd}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            started = time.monotonic()
            proc = subprocess.Popen([self.python, "-X", "utf8", str(Path(__file__).with_name("hi3d_tool.py"))], **options)
            data = json.dumps(payload).encode("utf-8")
            while True:
                if cancel.is_set() or time.monotonic() - started >= self.TIMEOUT:
                    proc.kill()
                    proc.communicate(timeout=5)
                    return self._interrupted(record, arguments, cancelled=cancel.is_set())
                try:
                    stdout, _ = proc.communicate(input=data, timeout=min(0.1, max(0.001, self.TIMEOUT - (time.monotonic() - started))))
                    break
                except subprocess.TimeoutExpired:
                    data = None
            result = json.loads(stdout)
            if proc.returncode != 0 or not isinstance(result, dict) or type(result.get("success")) is not bool:
                raise ValueError("Invalid worker result")
            if not result["success"]:
                recovery = self._interrupted(record, arguments)
                for key in ("task_id", "job_record", "generation_may_be_billable", "note"):
                    if key in recovery:
                        result.setdefault(key, recovery[key])
            return result
        except (OSError, ValueError, subprocess.SubprocessError):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=5)
            result = self._interrupted(record, arguments)
            result.pop("timed_out", None)
            result.update(stage="worker", error="Hi3D worker could not finish; inspect the recorded job before retrying.")
            return result
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
                for pipe in (proc.stdin, proc.stdout):
                    if pipe:
                        pipe.close()
            self._lock.release()

    @staticmethod
    def _interrupted(path, arguments, cancelled=False):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            record = {}
        state = record.get("state", "worker")
        stage = {"submitting": "submit", "accepted": "poll", "created": "poll", "queueing": "poll",
                 "processing": "poll", "failed": "poll", "success": "download", "downloaded": "readback"}.get(state, state)
        result = {"success": False, "stage": stage,
                  "error": "Stopped locally; the provider job may continue." if cancelled else "Hi3D time limit reached.",
                  "job_record": str(path)}
        result["cancelled" if cancelled else "timed_out"] = True
        task_id = record.get("task_id") or arguments.get("task_id")
        if task_id:
            result["task_id"] = task_id
        if task_id or record.get("submission_started"):
            result["generation_may_be_billable"] = True
            result["note"] = "Resume this task_id." if task_id else "Check Hi3D task history before submitting again."
        return result
