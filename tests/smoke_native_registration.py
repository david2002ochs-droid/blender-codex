"""Opt-in installed Codex handshake; registers the tool but makes no model/API call."""
import importlib.util
from pathlib import Path
import queue
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender_codex"))
import native_tools

spec = importlib.util.spec_from_file_location("native_registration_smoke", ROOT / "blender_codex/codex_client.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Client(module.CodexClient):
    def _run(self, args, *rest):
        return super()._run(args + ["-c", "mcp_servers={}"], *rest)

    def _request(self, method, params, callback):
        if method == "thread/start":
            params = {**params, "ephemeral": True}
        return super()._request(method, params, callback)

with tempfile.TemporaryDirectory() as directory:
    events = queue.Queue()
    runner = native_tools.NativeTools(directory, credentials=("", ""))
    client = Client(events.put, native_tools=runner)
    try:
        client.start(codex_path=sys.argv[1] if len(sys.argv) > 1 else "codex", cwd=str(ROOT), mcp_command="")
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            event = events.get(timeout=5)
            if event["type"] == "ready":
                print("NATIVE_REGISTRATION_PASS: installed Codex accepted experimentalApi + dynamicTools; no model turn, no Hi3D call")
                break
            if event["type"] in ("error", "closed"):
                raise RuntimeError(event.get("text", "Connection closed before registration"))
        else:
            raise TimeoutError("Registration timed out")
    finally:
        client.close()
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            try:
                if events.get(timeout=0.2)["type"] == "closed":
                    break
            except queue.Empty:
                pass
