"""Real plugin-created thread/name/resume proof; no turn, tools or scene calls."""
import argparse
import importlib.util
from pathlib import Path
import queue
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("codex_history_smoke", ROOT / "blender_codex/codex_client.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--codex", default="codex")
    options = parser.parse_args()
    clients = []
    target = {"BLENDER_MCP_HOST": "127.0.0.1", "BLENDER_MCP_PORT": str(options.port)}

    def wait(events, kind):
        deadline = time.monotonic() + 70
        while time.monotonic() < deadline:
            event = events.get(timeout=max(0.1, deadline - time.monotonic()))
            if event["type"] == kind:
                return event
            if event["type"] in ("error", "closed"):
                raise RuntimeError(event.get("text", "App-server closed before history verification"))
        raise TimeoutError("No " + kind)

    try:
        first_events = queue.Queue()
        first = module.CodexClient(first_events.put)
        clients.append(first)
        first.start(codex_path=options.codex, cwd=str(ROOT), mcp_env=target)
        thread_id = wait(first_events, "ready")["thread_id"]
        first.rename("Blender plugin history smoke")
        wait(first_events, "thread_renamed")
        first.close()
        wait(first_events, "closed")
        second_events = queue.Queue()
        second = module.CodexClient(second_events.put)
        clients.append(second)
        second.start(codex_path=options.codex, cwd=str(ROOT), mcp_env=target, resume_thread_id=thread_id)
        history = wait(second_events, "history")
        ready = wait(second_events, "ready")
        assert history["thread_id"] == thread_id and history["turns"] == []
        assert ready["resumed"] is True and ready["thread_id"] == thread_id
        print("REAL_HISTORY_PASS: thread/start + thread/name/set; fresh child thread/resume + full thread/turns/list; "
              "same thread %s; no turn/model/tool/scene operation" % thread_id)
    finally:
        for client in clients:
            client.close()
        for client in clients:
            if client._proc is not None:
                try:
                    client._proc.wait(timeout=5)
                except Exception:
                    pass


if __name__ == "__main__":
    main()
