"""Local-only HTTP bridge. No bpy calls or imports on server threads.

Integration (on Blender's main-thread timer)::

    bridge = WebBridge()
    url = bridge.start()  # http://127.0.0.1:<port>/#token=<random token>
    command, reply = bridge.commands.get_nowait()
    reply.put({"ok": True})  # or {"ok": False, "error": "user-safe message"}
    bridge.publish(state)

The frontend reads the fragment token and uses X-Codex-Token for every API call.
POST /api/action uses {"action": "send", "text": "...", "include_view": false}.
Other actions: connect, disconnect, new_chat, stop, draw, hide_panel, provider_settings, approve
(request_id, approved), settings (all three flat string fields codex_path,
mcp_command, mcp_args). Static assets: index.html, app.js, styles.css
(style.css is also supported), favicon.svg. Requests time out after 4 seconds;
an already claimed main-thread action may still finish. Never blindly retry it.
"""

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import secrets
import socket
import threading
import time
from urllib.parse import urlsplit, quote
if __package__:
    from .session_state import ResourceStore
    from .state_projection import bounded_state
else:
    import importlib.util
    _state_spec = importlib.util.spec_from_file_location("_codex_bridge_state", Path(__file__).with_name("session_state.py"))
    _state_module = importlib.util.module_from_spec(_state_spec)
    _state_spec.loader.exec_module(_state_module)
    ResourceStore = _state_module.ResourceStore
    _projection_spec = importlib.util.spec_from_file_location("_codex_bridge_projection", Path(__file__).with_name("state_projection.py"))
    _projection_module = importlib.util.module_from_spec(_projection_spec)
    _projection_spec.loader.exec_module(_projection_module)
    bounded_state = _projection_module.bounded_state


_ASSET_ROOT = Path(__file__).resolve().parent / "web"
_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
_CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' blob: data:; font-src 'self' data:; "
        "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _initial_state():
    return {"ready": False, "busy": False, "status": "Disconnected", "error": "", "activity": "",
            "messages": [], "approvals": [], "models": [], "selected_model": None,
            "reasoning_effort": None, "permission_mode": "full_access", "permission_modes": [],
            "thread_id": None, "history_supported": False, "tool_calls": [], "artifacts": [], "attachments": [], "capabilities": {},
            "threads": [], "active_thread_id": None, "history_loading": False, "history_error": "", "markup_active": False,
            "context": {"filepath": "", "is_unsaved": True, "active_object": None, "selected_objects": []},
            "settings": {"codex_path": "codex", "mcp_command": "", "mcp_args": []}}


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _validate_action(command):
    if not isinstance(command, dict) or not isinstance(command.get("action"), str):
        raise ValueError("Expected a JSON object with an action.")
    action = command["action"]
    fields = {"connect": set(), "disconnect": set(), "new_chat": set(), "stop": set(), "draw": set(), "hide_panel": set(), "provider_settings": set(),
              "send": {"text", "include_view", "attachment_ids"}, "approve": {"request_id", "approved"},
              "settings": {"codex_path", "mcp_command", "mcp_args"},
              "select_model": {"model", "model_id", "reasoning_effort"}, "select_effort": {"reasoning_effort"},
              "set_permission": {"permission_mode"}, "set_permission_mode": {"permission_mode"},
              "attach_file": {"name", "mime", "data_base64"}, "upload_attachment": {"name", "mime_type", "data_base64"},
              "remove_attachment": {"resource_id"}, "respond": {"request_id", "approved", "values", "answers"}}
    fields.update({"threads/list": set(), "threads/new": set(), "threads/open": {"thread_id"}, "threads/rename": {"thread_id", "title"}, "markup_cancel": set()})
    if action not in fields or set(command) - (fields[action] | {"action"}):
        raise ValueError("Unknown action or action fields.")
    if action in ("threads/open", "threads/rename"):
        if not isinstance(command.get("thread_id"), str) or not command["thread_id"] or len(command["thread_id"]) > 256:
            raise ValueError("Invalid plugin thread identity.")
        if action == "threads/rename" and (not isinstance(command.get("title"), str) or not command["title"].strip()
                or len(command["title"]) > 200 or any(ord(c) < 32 for c in command["title"])):
            raise ValueError("Use a chat name of 1–200 characters.")
    elif action == "send":
        text = command.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 32768:
            raise ValueError("Enter a message of at most 32768 characters.")
        if not isinstance(command.get("include_view", False), bool):
            raise ValueError("include_view must be a boolean.")
        if "attachment_ids" in command and (not isinstance(command["attachment_ids"], list) or len(command["attachment_ids"]) > 16
                or not all(isinstance(x, str) and len(x) <= 96 for x in command["attachment_ids"])):
            raise ValueError("Invalid attachment handles.")
    elif action in ("approve", "respond"):
        request_id = command.get("request_id")
        if (type(request_id) not in (int, str) or
                (isinstance(request_id, str) and (not request_id or len(request_id) > 256))
                or not isinstance(command.get("approved"), bool)):
            raise ValueError("A valid request_id and boolean approved value are required.")
        for key in ("values", "answers"):
            if key in command and not isinstance(command[key], dict):
                raise ValueError("Form values and question answers must be objects.")
    elif action in ("select_model", "select_effort", "set_permission", "set_permission_mode", "remove_attachment"):
        required = "permission_mode" if action.startswith("set_permission") else "resource_id" if action == "remove_attachment" else "reasoning_effort" if action == "select_effort" else ("model_id" if "model_id" in command else "model")
        if not isinstance(command.get(required), str) or not command[required] or len(command[required]) > 256:
            raise ValueError("Invalid selection or resource handle.")
        if "reasoning_effort" in command and (not isinstance(command["reasoning_effort"], str) or len(command["reasoning_effort"]) > 64):
            raise ValueError("Invalid reasoning effort.")
    elif action in ("attach_file", "upload_attachment"):
        if not all(isinstance(command.get(key), str) for key in ("name", "data_base64")):
            raise ValueError("A filename and base64 attachment are required.")
        mime = command.get("mime", command.get("mime_type", ""))
        if not isinstance(mime, str) or len(mime) > 128 or len(command["name"]) > 255:
            raise ValueError("Invalid attachment metadata.")
    elif action == "settings":
        if not all(key in command for key in ("codex_path", "mcp_command", "mcp_args")):
            raise ValueError("Provide all three connection settings as strings.")
        for key in ("codex_path", "mcp_command"):
            if key in command and (not isinstance(command[key], str) or len(command[key]) > 4096
                                   or any(c in command[key] for c in "\x00\r\n")):
                raise ValueError("Invalid command path setting.")
        if "mcp_args" in command:
            args = command["mcp_args"]
            if not (isinstance(args, str) and len(args) <= 8192 and "\x00" not in args):
                raise ValueError("mcp_args must be a string containing the arguments.")
    return command


class _LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(self, bridge):
        self.bridge = bridge
        self.token = bridge.token
        self.stopped = threading.Event()
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", 0), _Handler)
        self.authority = "127.0.0.1:%d" % self.server_port
        self.origin = "http://" + self.authority

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2.0)
        return connection, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Never dump a request, prompt, access token, or exception to stderr.
        pass


class _Handler(BaseHTTPRequestHandler):
    server_version = "BlenderCodex"
    sys_version = ""
    protocol_version = "HTTP/1.0"  # one bounded request per connection

    def log_message(self, format, *args):
        pass

    def _reply(self, status, body, content_type="application/json; charset=utf-8", extra_headers=None):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("Content-Security-Policy", _CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
        except (OSError, socket.timeout):
            pass
        self.close_connection = True

    def _error(self, status, text):
        self._reply(status, _json_bytes({"ok": False, "error": text}))

    def send_error(self, code, message=None, explain=None):
        # Base class error pages can reflect request-target input. Keep errors fixed.
        self._error(code, "HTTP request rejected.")

    def _check(self, authenticated=False):
        if self.server.stopped.is_set():
            self._error(503, "The Blender bridge stopped.")
            return False
        if self.headers.get_all("Host", []) != [self.server.authority]:
            self._error(403, "Invalid local Host header.")
            return False
        origins = self.headers.get_all("Origin", [])
        if origins and origins != [self.server.origin]:
            self._error(403, "Cross-origin requests are not permitted.")
            return False
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            self._error(403, "Cross-origin requests are not permitted.")
            return False
        if authenticated:
            tokens = self.headers.get_all("X-Codex-Token", [])
            supplied = tokens[0] if len(tokens) == 1 else ""
            if not hmac.compare_digest(supplied.encode("utf-8"), self.server.token.encode("ascii")):
                self._error(401, "Local API authentication required.")
                return False
        return True

    def _path(self):
        # Absolute-form, query strings, fragments, escapes, and traversal are not
        # needed by this small UI. Exact matching avoids decoding ambiguities.
        if len(self.path) > 2048 or not self.path.startswith("/") or self.path.startswith("//"):
            return None
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment or parsed.path != self.path:
            return None
        return self.path

    def do_GET(self):
        path = self._path()
        resource = path is not None and (path.startswith("/api/resource/") or path.startswith("/api/resources/"))
        if not self._check(authenticated=path == "/api/state" or resource):
            return
        if path == "/api/state":
            with self.server.bridge._state_lock:
                snapshot = self.server.bridge._state
            self._reply(200, snapshot)
        elif resource:
            handle = path.rsplit("/", 1)[-1]
            try:
                if len(handle) != 48 or any(c not in "0123456789abcdef" for c in handle):
                    raise KeyError()
                descriptor, _, data = self.server.bridge.resources.get(handle)
            except KeyError:
                self._error(404, "Resource handle is unavailable in this session.")
                return
            self._reply(200, data, descriptor["mime"], {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(descriptor["name"], safe="")})
        elif path in self.server.bridge._assets:
            filename, content_type = self.server.bridge._assets[path]
            try:
                # Resolve symlinks too; packaged assets must stay inside web/.
                root = _ASSET_ROOT.resolve()
                asset = (root / filename).resolve()
                if not asset.is_relative_to(root) or not asset.is_file():
                    raise OSError()
                with asset.open("rb") as source:
                    body = source.read(self.server.bridge.MAX_ASSET_BYTES + 1)
                if len(body) > self.server.bridge.MAX_ASSET_BYTES:
                    raise OSError()
            except OSError:
                self._error(404, "Local UI asset not found.")
                return
            self._reply(200, body, content_type)
        else:
            self._error(404, "Route not found.")

    def do_POST(self):
        if not self._check(authenticated=True):
            return
        if self._path() != "/api/action":
            self._error(404, "Route not found.")
            return
        if self.headers.get_all("Transfer-Encoding", []):
            self._error(400, "Transfer encoding is not supported.")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or len(lengths[0]) > 10 or not lengths[0].isascii()
                or not lengths[0].isdigit()):
            self._error(411, "One valid Content-Length header is required.")
            return
        length = int(lengths[0])
        if not 0 < length <= self.server.bridge.MAX_BODY_BYTES:
            self._error(413, "Action request exceeds the size limit or is empty.")
            return
        if (len(self.headers.get_all("Content-Type", [])) != 1 or
                self.headers.get_content_type() != "application/json"):
            self._error(415, "Use application/json for actions.")
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError()
            command = _validate_action(json.loads(raw.decode("utf-8")))
        except (ValueError, UnicodeError, OSError, RecursionError):
            self._error(400, "Invalid JSON action or action fields.")
            return
        bridge = self.server.bridge
        reply = queue.Queue(maxsize=1)
        entry = (command, reply)
        with bridge._lifecycle_lock:
            # Serialize enqueue with stop's final queue drain. An old handler
            # must never add work after shutdown and have it run on restart.
            if self.server.stopped.is_set():
                self._error(503, "The Blender bridge is stopping.")
                return
            try:
                bridge.commands.put_nowait(entry)
            except queue.Full:
                self._error(503, "Blender has too many pending actions. Try again later.")
                return
        deadline = time.monotonic() + min(bridge.ACTION_TIMEOUT, 4.5)
        while not self.server.stopped.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                result = reply.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            try:
                if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                    raise ValueError()
                body = _json_bytes(result)
                if len(body) > bridge.MAX_BODY_BYTES:
                    raise ValueError()
            except (ValueError, TypeError, RecursionError):
                self._error(500, "Blender returned an invalid action result.")
                return
            self._reply(200 if result["ok"] else 400, body)
            return
        bridge._discard(entry)
        if self.server.stopped.is_set():
            self._error(503, "The Blender bridge stopped.")
        else:
            self._error(504, "Blender did not respond in time. An action already picked up may still finish; check state before retrying.")

    def do_OPTIONS(self):
        # No CORS preflight support, even with a valid token.
        if self._check():
            self._error(405, "Cross-origin API access is not supported.")


class WebBridge:
    MAX_BODY_BYTES = 12 * 1024 * 1024
    # Original Deepblick React/Lexical bundle currently occupies about 10 MiB.
    # Static package assets have a separate bound from JSON/uploads/resources.
    MAX_ASSET_BYTES = 16 * 1024 * 1024
    MAX_STATE_BYTES = 4 * 1024 * 1024
    ACTION_TIMEOUT = 4.0

    def __init__(self):
        self.commands = queue.Queue(maxsize=32)
        self.resources = ResourceStore()
        self._assets = dict(_ASSETS)
        asset_dir = _ASSET_ROOT / "assets"
        if asset_dir.is_dir():
            for path in asset_dir.iterdir():
                if path.is_file() and path.suffix in (".js", ".css", ".woff2", ".png", ".svg"):
                    mime = {".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml"}[path.suffix]
                    self._assets["/assets/" + path.name] = ("assets/" + path.name, mime)
        self.token = secrets.token_hex(32)
        self.url = ""
        self._state_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._state = _json_bytes(_initial_state())
        self._server = None
        self._thread = None
        self._stopped = threading.Event()
        self._stopped.set()

    def publish(self, state):
        """Copy JSON state. Caller must not include credentials or other secrets."""
        if not isinstance(state, dict):
            raise ValueError("State must be a dictionary.")
        snapshot = _initial_state()
        for key in snapshot:
            if key in state:
                snapshot[key] = state[key]
        # Do not accidentally export arbitrary preferences/credentials alongside
        # the three explicitly supported connection settings.
        settings = snapshot["settings"]
        if not isinstance(settings, dict):
            raise ValueError("Settings must be a dictionary.")
        snapshot["settings"] = {key: settings[key] for key in ("codex_path", "mcp_command", "mcp_args") if key in settings}
        snapshot = bounded_state(snapshot, self.resources, self.MAX_STATE_BYTES)
        encoded = _json_bytes(snapshot)
        with self._state_lock:
            self._state = encoded

    def start(self):
        with self._lifecycle_lock:
            if self._server is not None:
                return self.url
            self.token = secrets.token_hex(32)
            server = _LocalServer(self)
            self._server = server
            self._stopped.clear()
            self.url = server.origin + "/#token=" + self.token
            self._thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1},
                                            name="BlenderCodex HTTP", daemon=True)
            self._thread.start()
            return self.url

    def _discard(self, entry):
        # Remove only this pending item, never another caller's command. If the
        # Blender timer already claimed it, it owns completion and may still reply.
        with self.commands.mutex:
            for index, pending in enumerate(self.commands.queue):
                if pending is entry:
                    del self.commands.queue[index]
                    self.commands.unfinished_tasks -= 1
                    self.commands.not_full.notify()
                    if self.commands.unfinished_tasks == 0:
                        self.commands.all_tasks_done.notify_all()
                    break

    def stop(self):
        with self._lifecycle_lock:
            server = self._server
            if server is None:
                return
            self._stopped.set()
            server.stopped.set()
            server.shutdown()
            server.server_close()
            self._thread.join(timeout=1)
            self._server = None
            self._thread = None
            # HTTP handlers notice the stop event; queued commands must never be
            # executed on a subsequent restart.
            with self.commands.mutex:
                count = len(self.commands.queue)
                self.commands.queue.clear()
                self.commands.unfinished_tasks -= count
                self.commands.not_full.notify_all()
                if self.commands.unfinished_tasks == 0:
                    self.commands.all_tasks_done.notify_all()
