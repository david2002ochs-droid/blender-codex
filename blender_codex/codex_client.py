"""Threaded, stdlib-only Codex app-server JSONL client (no bpy imports).

All public methods return immediately. Events may arrive on a worker thread;
callbacks must enqueue them for Blender's main thread. Each instance owns one
process/connection; create a fresh instance after ``closed``.
"""

import collections
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

if __package__:
    from .official_backend import resolve_launch
    from .request_forms import supported_form, validate_form, validate_answers
else:
    # Keep standalone stdlib smoke tests usable without importing bpy __init__.
    import importlib.util
    _backend_spec = importlib.util.spec_from_file_location(
        "_blender_codex_official_backend", os.path.join(os.path.dirname(__file__), "official_backend.py"))
    _backend_module = importlib.util.module_from_spec(_backend_spec)
    _backend_spec.loader.exec_module(_backend_module)
    resolve_launch = _backend_module.resolve_launch
    _form_spec = importlib.util.spec_from_file_location("_blender_codex_forms", os.path.join(os.path.dirname(__file__), "request_forms.py"))
    _form_module = importlib.util.module_from_spec(_form_spec)
    _form_spec.loader.exec_module(_form_module)
    supported_form, validate_form, validate_answers = _form_module.supported_form, _form_module.validate_form, _form_module.validate_answers


class CodexClient:
    REQUEST_TIMEOUT = 60.0
    IDLE_TIMEOUT = 600.0
    APPROVAL_TIMEOUT = 600.0
    # Four 8 MiB image resources expand to ~43 MiB in a single turn's JSON.
    # Framing is incremental; this is a hard per-record cap, not an allocation.
    MAX_LINE = 64 * 1024 * 1024
    READ_CHUNK = 64 * 1024
    HISTORY_PAGE_SIZE = 1
    HISTORY_MAX_TURNS = 1000
    HISTORY_MAX_BYTES = 128 * 1024 * 1024
    # Packaged, plugin-scoped instructions; never overwrite Codex global/base instructions.
    INSTRUCTIONS = Path(__file__).with_name("instructions.txt").read_text(encoding="utf-8").strip()
    if not INSTRUCTIONS:
        raise RuntimeError("Blender agent instructions are empty; reinstall the add-on.")


    def __init__(self, event_callback, native_tools=None):
        self._callback = event_callback
        self._native_tools = native_tools
        self._tool_calls = {}
        self._tool_call_ids = set()
        self._lock = threading.RLock()
        self._events = queue.Queue()
        self._writes = queue.Queue()
        self._proc = None
        self._started = False
        self._closing = False
        self._ready = False
        self._busy = False
        self._thread_id = None
        self._turn_id = None
        self._generation = 0
        self._interrupt_pending = False
        self._interrupt_sent = False
        self._pending = {}
        self._approvals = {}
        self._next_id = 0
        self._streamed = set()
        self._completed = set()
        self._stderr = collections.deque(maxlen=12)
        self._last_activity = time.monotonic()
        self.models = []
        self.selected_model = None
        self.reasoning_effort = None
        self.permission_mode = "full_access"
        self._model_cursors = set()
        self._sent_turns = set()
        self._resume_id = None
        self._history_turns = []
        self._history_cursors = set()
        self._history_bytes = 0

    def _emit(self, event_type, **values):
        try:
            self._callback(dict(type=event_type, **values))
        except Exception:
            # A broken UI callback must not strand the server or its pipes.
            pass

    def start(self, codex_path="codex", cwd=None, mcp_command=None, mcp_args=None,
              model=None, reasoning_effort=None, permission_mode="full_access", mcp_env=None,
              resume_thread_id=None):
        self.configure(permission_mode=permission_mode)
        self.selected_model, self.reasoning_effort = model, reasoning_effort
        if resume_thread_id is not None and (not isinstance(resume_thread_id, str) or not resume_thread_id or len(resume_thread_id) > 256):
            raise ValueError("Invalid thread resume identity.")
        self._resume_id = resume_thread_id
        with self._lock:
            if self._started or self._closing:
                self._emit("error", text="This client has already been started or closed.")
                return
            self._started = True
        args = [os.fspath(codex_path), "app-server"]
        target = dict(mcp_env) if mcp_env is not None else None if mcp_command == "" else {
            "BLENDER_MCP_HOST": os.environ.get("BLENDER_MCP_HOST", "127.0.0.1"),
            "BLENDER_MCP_PORT": os.environ.get("BLENDER_MCP_PORT", "9876")}
        threading.Thread(target=self._run, args=(args, cwd, mcp_command, mcp_args, target), daemon=True,
                         name="BlenderCodex transport").start()

    def send(self, text, context_dict, image_paths=None, attachment_texts=None):
        """Submit text/context plus only explicitly supplied local image paths."""
        try:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Enter a message first.")
            context = json.dumps(context_dict, ensure_ascii=False, allow_nan=False)
            images = self._local_images(image_paths)
            if attachment_texts is not None and (not isinstance(attachment_texts, list)
                    or not all(isinstance(x, str) and len(x) <= 262144 for x in attachment_texts)):
                raise ValueError("Text attachments exceed the supported size or format.")
        except (TypeError, ValueError) as exc:
            self._emit("error", text=str(exc))
            return
        with self._lock:
            if not self._ready or self._closing:
                self._emit("error", text="Codex is not connected yet.")
                return
            if self._busy:
                self._emit("error", text="A turn is already running. Stop it or wait for completion.")
                return
            self._busy = True
            self._generation += 1
            self._events.put(("send", (text, context, self._generation, images, attachment_texts or [])))
            return True

    def configure(self, model=None, reasoning_effort=None, permission_mode=None):
        """Validate selection now; apply it to the next real turn/start RPC."""
        with self._lock:
            if self._busy:
                raise ValueError("Wait for the active turn before changing model or permissions.")
            selected = self.selected_model if model is None else model
            effort = self.reasoning_effort if reasoning_effort is None else reasoning_effort
            if model is not None or reasoning_effort is not None:
                entry = next((m for m in self.models if m.get("id") == selected), None)
                if entry is None:
                    raise ValueError("Select a model from the connected Codex model catalog.")
                efforts = [e["reasoningEffort"] for e in entry.get("supportedReasoningEfforts", [])]
                if model is not None and reasoning_effort is None:
                    effort = entry.get("defaultReasoningEffort")
                if efforts and effort not in efforts:
                    raise ValueError("This model does not support the selected reasoning effort.")
                if not efforts:
                    if reasoning_effort is not None:
                        raise ValueError("This model does not expose a reasoning-effort selector.")
                    effort = None
            mode = self.permission_mode if permission_mode is None else permission_mode
            if mode not in ("full_access", "on_request", "read_only"):
                raise ValueError("Unknown permission mode.")
            self.selected_model, self.reasoning_effort, self.permission_mode = selected, effort, mode
        self._emit("configuration", selected_model=selected, reasoning_effort=effort, permission_mode=mode)

    def respond(self, request_id, approved, values=None, answers=None):
        self._events.put(("respond", (request_id, bool(approved), values, answers)))

    def rename(self, title):
        with self._lock:
            if not self._ready or self._busy or self._closing:
                raise ValueError("Wait for an idle connected chat before renaming it on the server.")
            if not isinstance(title, str) or not title.strip() or len(title) > 200:
                raise ValueError("Use a chat name of 1–200 characters.")
            self._events.put(("rename", title.strip()))





    @staticmethod
    def _local_images(image_paths):
        if image_paths is None:
            return []
        if not isinstance(image_paths, (list, tuple)):
            raise ValueError("Image attachments must be a list of local PNG, JPEG or WEBP paths.")
        images = []
        for value in image_paths:
            try:
                path = os.fspath(value)
                if not isinstance(path, str):
                    raise ValueError()
                path = os.path.abspath(path)
                if not os.path.isfile(path):
                    raise ValueError()
                with open(path, "rb") as source:
                    header = source.read(16)
                suffix = os.path.splitext(path)[1].lower()
                valid = ((suffix == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
                         or (suffix in (".jpg", ".jpeg") and header.startswith(b"\xff\xd8\xff"))
                         or (suffix == ".webp" and header.startswith(b"RIFF") and header[8:12] == b"WEBP"))
                if not valid:
                    raise ValueError()
            except (OSError, TypeError, ValueError):
                raise ValueError("An image attachment is missing, unreadable, or not a PNG, JPEG or WEBP file.") from None
            images.append({"type": "localImage", "path": path})
        return images

    def interrupt(self):
        self._events.put(("interrupt", None))

    def approve(self, request_id, approved):
        self._events.put(("approve", (request_id, bool(approved))))

    def close(self):
        with self._lock:
            if self._closing:
                return
            self._closing = True
            self._ready = False
            if not self._started:
                self._emit("closed")
                return
        self._events.put(("close", None))

    def _write(self, message):
        self._writes.put(json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n")

    def _request(self, method, params, callback):
        self._next_id += 1
        self._pending[self._next_id] = (time.monotonic(), method, callback)
        self._write(dict(id=self._next_id, method=method, params=params))

    def _read_stdout(self, proc):
        buffer = bytearray()
        def unique_members(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate JSON member")
                result[key] = value
            return result
        def reject_constant(value):
            raise ValueError("Non-finite JSON number")
        try:
            while True:
                chunk = proc.stdout.read1(self.READ_CHUNK)
                if not chunk:
                    if buffer:
                        raise ValueError("Unterminated JSONL record at end of stream")
                    self._events.put(("eof", None))
                    return
                buffer.extend(chunk)
                while True:
                    end = buffer.find(b"\n")
                    if end < 0:
                        if len(buffer) >= self.MAX_LINE:
                            raise ValueError("JSONL record exceeds the bounded wire limit")
                        break
                    if end + 1 > self.MAX_LINE:
                        raise ValueError("JSONL record exceeds the bounded wire limit")
                    line = bytes(buffer[:end])
                    del buffer[:end + 1]
                    try:
                        message = json.loads(line.decode("utf-8"), object_pairs_hook=unique_members, parse_constant=reject_constant)
                    except UnicodeError:
                        raise ValueError("Invalid UTF-8 JSONL record") from None
                    except (json.JSONDecodeError, RecursionError):
                        raise ValueError("Malformed or excessively nested JSONL record") from None
                    if not isinstance(message, dict):
                        raise ValueError("JSONL message must be an object")
                    self._events.put(("message", message))
        except ValueError as exc:
            # Only locally authored fixed diagnostics; never echo record bytes.
            self._events.put(("fatal", "Invalid app-server protocol: " + str(exc) +
                              ". Record limit: %d MiB; no partial history accepted." % (self.MAX_LINE // (1024 * 1024))))
        except Exception:
            self._events.put(("fatal", "Invalid app-server protocol: transport read failed; no record contents logged."))

    def _read_stderr(self, proc):
        try:
            while True:
                chunk = proc.stderr.read1(4096)
                if not chunk:
                    return
                self._stderr.append(chunk.decode("utf-8", errors="replace")[-2000:])
        except (OSError, ValueError):
            pass

    def _write_stdin(self, proc):
        try:
            while True:
                line = self._writes.get()
                if line is None:
                    proc.stdin.close()
                    return
                proc.stdin.write(line.encode("utf-8"))
                proc.stdin.flush()
        except (OSError, ValueError) as exc:
            self._events.put(("fatal", "Cannot write to Codex: " + str(exc)))

    def _run(self, args, cwd, mcp_command, mcp_args, mcp_env):
        readers = []
        try:
            mcp_command, mcp_args = resolve_launch(mcp_command, mcp_args)
            if mcp_command:
                # Official launch overrides affect this child only, never the
                # user's normal Codex CLI or global configuration files.
                for key, value in (("command", mcp_command), ("args", mcp_args),
                                   ("enabled", True), ("required", True)):
                    args.extend(["-c", "mcp_servers.blender." + key + "=" + json.dumps(value)])
            if mcp_env is not None:
                # App-server filters inherited MCP environment. Explicit CLI
                # overrides pin ONLY this child's Blender MCP to the socket
                # owned by the current Blender process, including custom ports.
                if set(mcp_env) != {"BLENDER_MCP_HOST", "BLENDER_MCP_PORT"}:
                    raise ValueError("Only Blender MCP host/port environment overrides are supported.")
                if mcp_env["BLENDER_MCP_HOST"] not in ("127.0.0.1", "localhost"):
                    raise ValueError("Blender MCP must target the local Blender listener.")
                port = mcp_env["BLENDER_MCP_PORT"]
                if not isinstance(port, str) or not port.isascii() or not port.isdigit() or not 1024 <= int(port) <= 65535:
                    raise ValueError("Invalid Blender MCP target port.")
                for key, value in mcp_env.items():
                    args.extend(["-c", "mcp_servers.blender.env." + key + "=" + json.dumps(value)])
            self._emit("status", text="Starting Codex app-server…")
            options = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, cwd=cwd, bufsize=-1)
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = subprocess.SW_HIDE
                options["startupinfo"] = startup
            proc = self._proc = subprocess.Popen(args, **options)
            for target in (self._read_stdout, self._read_stderr, self._write_stdin):
                worker = threading.Thread(target=target, args=(proc,), daemon=True)
                readers.append(worker)
                worker.start()
            self._request("initialize", {"clientInfo": {
                "name": "blender_codex", "title": "Blender Codex", "version": "0.1.0"},
                **({"capabilities": {"experimentalApi": True}} if self._native_tools else {})},
                lambda result: self._initialized(cwd))
            while True:
                kind, data = None, None
                try:
                    kind, data = self._events.get(timeout=0.2)
                except queue.Empty:
                    pass
                if kind == "close":
                    break
                if kind == "fatal":
                    raise RuntimeError(data)
                if kind == "eof":
                    raise RuntimeError("Codex app-server closed stdout unexpectedly. " +
                                       "".join(self._stderr)[-3000:])
                if kind == "message":
                    self._handle(data)
                elif kind == "send":
                    self._begin_turn(*data)
                elif kind == "interrupt":
                    if self._busy:
                        self._interrupt_pending = True
                        self._cancel_native_tools()
                        # Resolve blocking approvals first, then interrupt the turn.
                        for request_id in list(self._approvals):
                            self._answer_approval(request_id, False)
                        self._try_interrupt()
                elif kind == "approve":
                    self._answer_approval(*data)
                elif kind == "respond":
                    self._answer_approval(*data)
                elif kind == "rename":
                    self._request("thread/name/set", {"threadId": self._thread_id, "name": data},
                                  lambda result, title=data: self._emit("thread_renamed", thread_id=self._thread_id, title=title))
                elif kind == "native_result":
                    self._finish_native_tool(*data)
                now = time.monotonic()
                for started, method, _ in list(self._pending.values()):
                    if now - started > self.REQUEST_TIMEOUT:
                        raise TimeoutError("Codex timed out waiting for " + method)
                for request_id, (_, _, started) in list(self._approvals.items()):
                    if now - started > self.APPROVAL_TIMEOUT:
                        self._emit("error", text="Approval expired; request was declined.")
                        self._answer_approval(request_id, False)
                if self._busy and not self._approvals and not self._tool_calls and now - self._last_activity > self.IDLE_TIMEOUT:
                    raise TimeoutError("Codex stopped sending turn updates; reconnect and try again.")
        except Exception as exc:
            if not self._closing:
                self._emit("error", text=str(exc), fatal=True)
        finally:
            self._cancel_native_tools()
            with self._lock:
                self._closing = True
                self._ready = False
                busy, self._busy = self._busy, False
            self._pending.clear()
            self._approvals.clear()
            self._writes.put(None)
            proc = self._proc
            if proc is not None:
                # stdio app-server has no shutdown RPC: close stdin, then bound
                # the exit wait and terminate/kill an unresponsive child.
                try:
                    proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
                for reader in readers:
                    reader.join(timeout=0.3)
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    try:
                        pipe.close()
                    except (OSError, ValueError):
                        pass
            if busy:
                self._emit("done")
            self._emit("closed")

    def _initialized(self, cwd):
        self._write({"method": "initialized", "params": {}})
        self._request("account/read", {"refreshToken": False},
                      lambda result: self._account(result, cwd))

    def _account(self, result, cwd):
        if result.get("account") is None and result.get("requiresOpenaiAuth", True):
            raise RuntimeError("Codex is not signed in. Run 'codex login' with your existing "
                               "account, then reconnect. No API key is required.")
        self._request("model/list", {"includeHidden": False}, lambda result: self._models(result, cwd))

    def _models(self, result, cwd):
        entries = result.get("data")
        if not isinstance(entries, list):
            raise ValueError("model/list returned an invalid catalog")
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("model"), str):
                if not any(m["id"] == entry["id"] for m in self.models):
                    self.models.append(entry)
        cursor = result.get("nextCursor")
        if cursor:
            if cursor in self._model_cursors or len(self._model_cursors) >= 20:
                raise ValueError("model/list pagination did not finish")
            self._model_cursors.add(cursor)
            self._request("model/list", {"includeHidden": False, "cursor": cursor}, lambda result: self._models(result, cwd))
            return
        if self.selected_model is None and self.models:
            selected = next((m for m in self.models if m.get("isDefault")), self.models[0])
            self.selected_model = selected["id"]
        if self.selected_model is not None:
            self.configure(model=self.selected_model, reasoning_effort=self.reasoning_effort)
        self._emit("models", models=self.models, selected_model=self.selected_model,
                   reasoning_effort=self.reasoning_effort, permission_mode=self.permission_mode)
        # Fresh and resumed children use the current plugin prompt, even if
        # this class was imported before instructions.txt changed.
        instructions = Path(__file__).with_name("instructions.txt").read_text(encoding="utf-8").strip()
        if not instructions:
            raise RuntimeError("Blender agent instructions are empty; reinstall the add-on.")
        params = {"developerInstructions": instructions, **self._policy()}
        if self._native_tools and self._resume_id is None:
            params["dynamicTools"] = self._native_tools.specs
        model = next((m for m in self.models if m["id"] == self.selected_model), None)
        if model:
            params["model"] = model["model"]
        if cwd:
            params["cwd"] = os.fspath(cwd)
        if self._resume_id is not None:
            params.update(threadId=self._resume_id, excludeTurns=True)
            self._request("thread/resume", params, self._thread_resumed)
        else:
            self._request("thread/start", params, self._thread_started)

    def _thread_resumed(self, result):
        thread = result["thread"]
        if thread.get("id") != self._resume_id:
            raise ValueError("thread/resume returned another thread; no history was accepted")
        self._thread_id = self._resume_id
        self._emit("history_loading", thread_id=self._thread_id)
        # Pagination is authoritative even when resume returns a legacy turns
        # field; request full persisted items, oldest first, before becoming ready.
        self._request("thread/turns/list", {"threadId": self._thread_id, "itemsView": "full", "sortDirection": "asc", "limit": self.HISTORY_PAGE_SIZE}, self._history_page)

    def _history_page(self, result):
        turns = result.get("data")
        if not isinstance(turns, list):
            raise ValueError("Invalid authoritative history response")
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("id"), str) or not isinstance(turn.get("items"), list) or turn.get("itemsView", "full") != "full":
                raise ValueError("App-server did not return full persisted history items")
            if not all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in turn["items"]):
                raise ValueError("Invalid persisted history item identity")
            if turn.get("status") == "inProgress":
                raise ValueError("This chat still has an active server turn; resume it only after that turn finishes.")
            if not any(previous["id"] == turn["id"] for previous in self._history_turns):
                size = len(json.dumps(turn, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                if self._history_bytes + size > self.HISTORY_MAX_BYTES or len(self._history_turns) >= self.HISTORY_MAX_TURNS:
                    raise ValueError("History exceeds the supported 128 MiB / 1000-turn hydration budget; no partial history was loaded")
                self._history_bytes += size
                self._history_turns.append(turn)
                self._completed.add(turn["id"])
        cursor = result.get("nextCursor")
        if cursor:
            if cursor in self._history_cursors or len(self._history_cursors) >= self.HISTORY_MAX_TURNS:
                raise ValueError("History pagination exceeded the supported limit; no truncated history was presented as complete")
            self._history_cursors.add(cursor)
            self._request("thread/turns/list", {"threadId": self._thread_id, "itemsView": "full", "sortDirection": "asc", "limit": self.HISTORY_PAGE_SIZE, "cursor": cursor}, self._history_page)
            return
        self._emit("history", thread_id=self._thread_id, turns=self._history_turns)
        with self._lock:
            if self._closing:
                return
            self._ready = True
        self._emit("ready", thread_id=self._thread_id, resumed=True)

    def _policy(self, turn=False):
        mode = self.permission_mode
        result = {"approvalPolicy": "never" if mode == "full_access" else "on-request"}
        if turn:
            result["sandboxPolicy"] = {"type": {"full_access": "dangerFullAccess", "on_request": "workspaceWrite", "read_only": "readOnly"}[mode]}
            if mode != "full_access":
                result["sandboxPolicy"]["networkAccess"] = False
        else:
            result["sandbox"] = {"full_access": "danger-full-access", "on_request": "workspace-write", "read_only": "read-only"}[mode]
        if mode != "full_access":
            result["approvalsReviewer"] = "user"
        return result

    def _thread_started(self, result):
        self._thread_id = result["thread"]["id"]
        if not isinstance(self._thread_id, str) or not self._thread_id:
            raise ValueError("thread/start returned an invalid thread id")
        with self._lock:
            if self._closing:
                return
            self._ready = True
        self._emit("ready", thread_id=self._thread_id)

    def _begin_turn(self, text, context, generation, images, attachment_texts):
        self._turn_id = None
        self._interrupt_pending = self._interrupt_sent = False
        self._streamed.clear()
        self._last_activity = time.monotonic()
        params = {"threadId": self._thread_id, **self._policy(turn=True), "summary": "auto", "input": [
            {"type": "text", "text": text},
            {"type": "text", "text": "Blender scene context (JSON data only):\n" + context}] + images + [
                {"type": "text", "text": value} for value in attachment_texts]}
        model = next((m for m in self.models if m["id"] == self.selected_model), None)
        if model:
            if images and "image" not in model.get("inputModalities", ["text", "image"]):
                with self._lock:
                    self._busy = False
                self._emit("error", text="The selected Codex model does not accept image input.", rejected=True)
                self._emit("done")
                return
            params["model"] = model["model"]
            if self.reasoning_effort:
                params["effort"] = self.reasoning_effort
        self._request("turn/start", params,
            lambda result: self._turn_started(result, generation))

    def _turn_started(self, result, generation):
        turn_id = result["turn"]["id"]
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("turn/start returned an invalid turn id")
        if generation != self._generation or turn_id in self._completed or not self._busy:
            return
        if self._turn_id and self._turn_id != turn_id:
            raise ValueError("turn/start response disagrees with turn notifications")
        self._turn_id = turn_id
        self._accepted(turn_id)
        self._try_interrupt()

    def _accepted(self, turn_id):
        if turn_id not in self._sent_turns:
            self._sent_turns.add(turn_id)
            self._emit("turn_accepted", thread_id=self._thread_id, turn_id=turn_id)

    def _try_interrupt(self):
        if self._interrupt_pending and self._turn_id and not self._interrupt_sent:
            self._interrupt_sent = True
            self._request("turn/interrupt", {"threadId": self._thread_id,
                                           "turnId": self._turn_id}, lambda result: None)
            self._emit("status", text="Stopping turn…")

    def _handle(self, message):
        if not isinstance(message, dict):
            raise ValueError("JSONL message must be an object")
        if "method" in message:
            method = message["method"]
            params = message.get("params", {})
            if not isinstance(method, str) or not isinstance(params, dict):
                raise ValueError("Invalid method or params")
            if "id" in message:
                self._server_request(message["id"], method, params)
            else:
                self._notification(method, params)
            return
        request_id = message.get("id")
        if type(request_id) not in (int, str):
            raise ValueError("Invalid response id")
        pending = self._pending.pop(request_id, None)
        if pending is None:
            raise ValueError("Response for an unknown request id")
        if ("error" in message) == ("result" in message):
            raise ValueError("Response must contain exactly one of result/error")
        if "error" in message:
            error = message["error"]
            raise RuntimeError(pending[1] + ": " + json.dumps(error, ensure_ascii=False))
        if not isinstance(message["result"], dict):
            raise ValueError("Response result must be an object")
        pending[2](message["result"])

    def _notification(self, method, params):
        if params.get("threadId") != self._thread_id:
            return
        if method == "serverRequest/resolved":
            request_id = params.get("requestId")
            native = self._tool_calls.pop(request_id, None)
            if native:
                native[1].set()
            if self._approvals.pop(request_id, None) is not None:
                self._emit("approval_resolved", request_id=request_id)
            return
        if not self._busy:
            return
        turn = params.get("turn", {})
        turn_id = params.get("turnId") or turn.get("id")
        if not turn_id or turn_id in self._completed:
            return
        if self._turn_id is not None and turn_id != self._turn_id:
            return
        self._turn_id = turn_id
        self._accepted(turn_id)
        self._last_activity = time.monotonic()
        if method != "turn/completed":
            self._try_interrupt()
        if method in ("item/reasoning/summaryTextDelta", "item/reasoning/summaryPartAdded"):
            # Only public summaries. Never forward textDelta/content/encryptedContent.
            index = params.get("summaryIndex")
            if type(index) is int and 0 <= index < 32 and isinstance(params.get("itemId"), str):
                delta = params.get("delta", "")
                if isinstance(delta, str):
                    self._emit("reasoning", phase="delta" if method.endswith("summaryTextDelta") else "part",
                               thread_id=self._thread_id, turn_id=turn_id, item_id=params["itemId"],
                               summary_index=index, text=delta[:16384], truncated=len(delta) > 16384)
        elif method == "item/agentMessage/delta":
            delta = params["delta"]
            if not isinstance(delta, str):
                raise ValueError("Invalid agent message delta")
            if delta:
                self._streamed.add(params["itemId"])
                self._emit("delta", text=delta, thread_id=self._thread_id, turn_id=turn_id, item_id=params["itemId"])
        elif method == "item/completed":
            item = params["item"]
            if item.get("type") == "reasoning":
                self._reasoning_item(item, turn_id, "completed")
            if item.get("type") == "dynamicToolCall":
                # Normalize function-tool readbacks for the existing chat renderer.
                content = [{"type": "text", "text": value.get("text", "")}
                           for value in (item.get("contentItems") or [])
                           if isinstance(value, dict) and value.get("type") == "inputText"]
                result = {"content": content, "isError": item.get("success") is False}
                if len(content) == 1:
                    try:
                        structured = json.loads(content[0]["text"])
                        if isinstance(structured, dict):
                            result["structuredContent"] = structured
                    except (ValueError, TypeError):
                        pass
                item = dict(item, result=result)
            if item.get("type") == "userMessage":
                self._emit("user_item", thread_id=self._thread_id, turn_id=turn_id, item_id=item["id"])
            if item.get("type") == "agentMessage" and item.get("id") not in self._streamed:
                self._emit("message", text=item.get("text", ""), thread_id=self._thread_id, turn_id=turn_id, item_id=item.get("id"))
            elif item.get("type") == "agentMessage":
                self._emit("message_final", text=item.get("text", ""), thread_id=self._thread_id, turn_id=turn_id, item_id=item.get("id"))
            if item.get("type") not in ("agentMessage", "userMessage", "reasoning", "plan"):
                self._emit("tool", phase="completed", thread_id=self._thread_id, turn_id=turn_id, item_id=item["id"], item=item)
        elif method == "item/started":
            item = params["item"]
            if item.get("type") == "reasoning":
                self._reasoning_item(item, turn_id, "started")
            if item.get("type") == "userMessage":
                self._emit("user_item", thread_id=self._thread_id, turn_id=turn_id, item_id=item["id"])
            if item.get("type") not in ("agentMessage", "userMessage", "reasoning", "plan"):
                self._emit("tool", phase="started", thread_id=self._thread_id, turn_id=turn_id, item_id=item["id"], item=item)
                self._emit("activity", text=item.get("type", "Working") + ": " +
                           str(item.get("tool") or item.get("command") or ""))
        elif method == "item/mcpToolCall/progress":
            self._emit("tool_progress", thread_id=self._thread_id, turn_id=turn_id, item_id=params["itemId"], text=str(params.get("message", "")))
            self._emit("activity", text=str(params.get("message", "Blender tool running…")))
        elif method == "item/commandExecution/outputDelta":
            self._emit("tool_progress", thread_id=self._thread_id, turn_id=turn_id, item_id=params["itemId"], text=str(params.get("delta", "")))
        elif method == "error":
            text = json.dumps(params.get("error", params), ensure_ascii=False)
            self._emit("activity" if params.get("willRetry") is True else "error", text=text)
        elif method == "turn/completed":
            # A final Turn may include authoritative readbacks even if an item
            # completion was missed. Replace by identity, never append a copy.
            for item in turn.get("items", []):
                if isinstance(item, dict) and item.get("type") == "reasoning":
                    self._reasoning_item(item, turn_id, "completed")
            self._completed.add(turn_id)
            self._cancel_native_tools()
            for request_id in list(self._approvals):
                self._answer_approval(request_id, False)
            with self._lock:
                self._busy = False
            if turn.get("error"):
                self._emit("error", text=json.dumps(turn["error"], ensure_ascii=False))
            elif turn.get("status") == "failed":
                self._emit("error", text="Codex turn failed without an error description.")
            self._emit("done", thread_id=self._thread_id, turn_id=turn_id, status=turn.get("status", "completed"),
                       started_at=turn.get("startedAt"), completed_at=turn.get("completedAt"), duration_ms=turn.get("durationMs"))

    def _reasoning_item(self, item, turn_id, phase):
        summary = item.get("summary", [])
        if not isinstance(summary, list):
            summary = []
        remaining, bounded = 16384, []
        truncated = len(summary) > 32
        for part in summary[:32]:
            if isinstance(part, str):
                bounded.append(part[:remaining])
                truncated |= len(part) > remaining
                remaining -= len(bounded[-1])
        self._emit("reasoning", phase=phase, thread_id=self._thread_id, turn_id=turn_id,
                   item_id=item.get("id"), summary=bounded, truncated=truncated)

    def _server_request(self, request_id, method, params):
        if type(request_id) not in (str, int):
            raise ValueError("Invalid server request id")
        if method == "item/tool/call" and self._native_tools:
            self._native_tool_request(request_id, params)
            return
        supported = ("item/commandExecution/requestApproval", "item/fileChange/requestApproval",
                     "item/permissions/requestApproval", "execCommandApproval", "applyPatchApproval",
                     "mcpServer/elicitation/request", "item/tool/requestUserInput")
        if method not in supported:
            # The boolean UI cannot collect form fields, token refreshes, or
            # dynamic tool outputs. Explicitly fail instead of leaving an RPC open.
            self._write({"id": request_id, "error": {"code": -32601,
                         "message": "Unsupported client request: " + method}})
            self._emit("error", text="Codex requested an unsupported client action: " + method)
            return
        if request_id in self._approvals:
            raise ValueError("Duplicate server approval request id")
        turn_id = params.get("turnId")
        if (not self._busy or params.get("threadId", self._thread_id) != self._thread_id
                or turn_id in self._completed
                or (turn_id is not None and self._turn_id is not None and turn_id != self._turn_id)):
            self._write({"id": request_id, "error": {"code": -32602,
                         "message": "Approval does not belong to the active Blender turn"}})
            return
        if method == "mcpServer/elicitation/request":
            schema = params.get("requestedSchema")
            if params.get("mode") != "form" or not supported_form(schema):
                # A yes/no answer must never invent form values or claim that
                # the user completed an external authentication flow.
                self._write({"id": request_id, "result": {"action": "cancel"}})
                self._emit("message", text="MCP-Rückfrage von " + str(params.get("serverName", "MCP"))
                           + ": " + str(params.get("message", ""))
                           + "\nDiese Rückfrage benötigt Formulareingaben oder eine externe Anmeldung; "
                             "sie wurde ohne Freigabe abgebrochen.")
                return
        self._approvals[request_id] = (method, params, time.monotonic())
        self._emit("approval", request_id=request_id,
                   kind=("form" if method == "mcpServer/elicitation/request" else
                         "questions" if method == "item/tool/requestUserInput" else "approval"),
                   schema=params.get("requestedSchema"), questions=params.get("questions"),
                   thread_id=self._thread_id, turn_id=turn_id, item_id=params.get("itemId"),
                   text=("MCP · " + str(params.get("serverName", "")) + "\n"
                         + str(params.get("message", "Bestätigung erforderlich")))
                   if method == "mcpServer/elicitation/request" else
                   method + "\n" + json.dumps(params, ensure_ascii=False, indent=2))

    def _answer_approval(self, request_id, approved, values=None, answers=None):
        approval = self._approvals.get(request_id)
        if approval is None:
            self._emit("error", text="This approval is no longer pending.")
            return
        method, params, _ = approval
        if method == "item/tool/call":
            self._approvals.pop(request_id, None)
            self._emit("approval_resolved", request_id=request_id)
            if approved and not self._interrupt_pending:
                self._start_native_tool(request_id)
            else:
                self._finish_native_tool(request_id, {"success": False, "stage": "approval", "error": "Tool call declined."})
            return
        if method == "mcpServer/elicitation/request":
            try:
                content = validate_form(params["requestedSchema"], {} if values is None else values) if approved else None
            except (ValueError, TypeError):
                self._emit("error", text="Please complete the required MCP form fields; the request remains pending.")
                return
            result = {"action": "accept", "content": content} if approved else {"action": "decline"}
        elif method == "item/tool/requestUserInput":
            try:
                result = {"answers": validate_answers(params["questions"], answers) if approved else {}}
            except (ValueError, TypeError, KeyError):
                self._emit("error", text="Please answer all requested questions; the request remains pending.")
                return
        elif method == "item/permissions/requestApproval":
            result = {"permissions": params.get("permissions", {}) if approved else {}, "scope": "turn"}
        elif method in ("execCommandApproval", "applyPatchApproval"):
            result = {"decision": "approved" if approved else {"denied": {"rejection": "User declined"}}}
        else:
            result = {"decision": "accept" if approved else "decline"}
        self._write({"id": request_id, "result": result})
        self._approvals.pop(request_id, None)
        self._emit("approval_resolved", request_id=request_id)
        self._last_activity = time.monotonic()

    def _native_tool_request(self, request_id, params):
        turn_id, call_id = params.get("turnId"), params.get("callId")
        if (not self._busy or self._interrupt_pending or params.get("threadId") != self._thread_id
                or not isinstance(turn_id, str) or turn_id in self._completed
                or (self._turn_id is not None and turn_id != self._turn_id)
                or not isinstance(call_id, str) or not call_id or call_id in self._tool_call_ids
                or request_id in self._tool_calls or request_id in self._approvals
                or params.get("namespace") not in (None, "")):
            self._write({"id": request_id, "error": {"code": -32602, "message": "Invalid or repeated native tool call."}})
            return
        self._tool_call_ids.add(call_id)
        self._tool_calls[request_id] = (params, threading.Event())
        if self.permission_mode == "read_only":
            self._finish_native_tool(request_id, {"success": False, "stage": "permissions", "error": "This tool needs network and file-write access."})
        elif self.permission_mode == "on_request":
            self._approvals[request_id] = ("item/tool/call", params, time.monotonic())
            self._emit("approval", request_id=request_id, kind="approval", thread_id=self._thread_id,
                       turn_id=turn_id, item_id=call_id,
                       text="Run " + str(params.get("tool")) + "? New Hi3D generations consume credits.\n"
                       + json.dumps(params.get("arguments"), ensure_ascii=False))
        else:
            self._start_native_tool(request_id)

    def _start_native_tool(self, request_id):
        call = self._tool_calls.get(request_id)
        if call is None:
            return
        params, cancel = call
        def run():
            try:
                result = self._native_tools.call(params.get("tool"), params.get("arguments"), cancel)
            except Exception:
                result = {"success": False, "stage": "worker", "error": "Native tool failed."}
            self._events.put(("native_result", (request_id, result)))
        threading.Thread(target=run, daemon=True, name="BlenderCodex native tool").start()

    def _finish_native_tool(self, request_id, result):
        if self._tool_calls.pop(request_id, None) is None:
            return  # Server already resolved/cancelled this request.
        self._write({"id": request_id, "result": {"success": result.get("success") is True,
                     "contentItems": [{"type": "inputText", "text": json.dumps(result, ensure_ascii=False, allow_nan=False)}]}})
        self._last_activity = time.monotonic()

    def _cancel_native_tools(self):
        for _, cancel in self._tool_calls.values():
            cancel.set()
