"""Opt-in real Codex handshake; does not submit a model turn or test MCP."""
import importlib.util
from pathlib import Path
import queue
import sys
import time

source = Path(__file__).resolve().parents[1] / "blender_codex" / "codex_client.py"
spec = importlib.util.spec_from_file_location("codex_transport_smoke", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
events = queue.Queue()
client = module.CodexClient(events.put)
try:
    client.start(codex_path=sys.argv[1] if len(sys.argv) > 1 else "codex",
                 cwd=str(source.parents[1]), mcp_command="")
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=1)
        except queue.Empty:
            continue
        kind = event["type"]
        if kind == "ready":
            print("CODEX_HANDSHAKE_PASS: initialize, account/read, thread/start; no model turn submitted")
            break
        if kind in ("error", "closed"):
            raise RuntimeError(event.get("text", "Codex closed before ready"))
    else:
        raise TimeoutError("Codex handshake did not become ready")
finally:
    client.close()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            if events.get(timeout=0.2)["type"] == "closed":
                break
        except queue.Empty:
            pass
