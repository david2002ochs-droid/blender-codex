"""Opt-in real official MCP handshake against a separate factory-startup Blender.

No model calls, Codex credentials, user .blend load/save, or *_for_cli tools.
This validates the connected-instance protocol in headless Blender, not UI/image
capture or the user's currently open interactive scene.
"""
import importlib.util
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("official_backend_smoke", ROOT / "blender_codex/official_backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


def drain(stream, output):
    for line in iter(stream.readline, b""):
        output.put(line.decode("utf-8", "replace"))


def stop(process):
    if process is not None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main():
    command, args = backend.resolve_launch()
    blender = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
    runtime = backend.DEFAULT_RUNTIME_ROOT
    source = runtime / "source"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    processes = []
    with tempfile.TemporaryDirectory(prefix="smoke-", dir=runtime) as directory:
        bootstrap = Path(directory) / "bootstrap.py"
        bootstrap.write_text(
            "import sys, os\n"
            "sys.path.insert(0, %r)\n" % str(source / "addon") +
            "from blender_mcp_addon import mcp_to_blender_server, execute_blocking\n"
            "mcp_to_blender_server.start('127.0.0.1', %d)\n" % port +
            "print('OFFICIAL_SMOKE_READY', os.getpid(), flush=True)\n"
            "try:\n    execute_blocking.run()\n"
            "finally:\n    mcp_to_blender_server.stop()\n", encoding="utf-8")
        try:
            blender_proc = subprocess.Popen([blender, "--background", "--factory-startup", "--online-mode",
                                             "--python", str(bootstrap)], stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
            processes.append(blender_proc)
            blender_output = queue.Queue()
            threading.Thread(target=drain, args=(blender_proc.stdout, blender_output), daemon=True).start()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                line = blender_output.get(timeout=max(0.1, deadline - time.monotonic()))
                if line.startswith("OFFICIAL_SMOKE_READY"):
                    blender_pid = int(line.split()[-1])
                    break
            else:
                raise RuntimeError("Isolated Blender did not start its official bridge")
            environment = dict(os.environ, BLENDER_MCP_HOST="127.0.0.1", BLENDER_MCP_PORT=str(port))
            mcp = subprocess.Popen([command, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=environment, creationflags=flags)
            processes.append(mcp)
            received, errors = queue.Queue(), queue.Queue()
            threading.Thread(target=drain, args=(mcp.stdout, received), daemon=True).start()
            threading.Thread(target=drain, args=(mcp.stderr, errors), daemon=True).start()

            def write(message):
                mcp.stdin.write((json.dumps(message) + "\n").encode())
                mcp.stdin.flush()

            def rpc(request_id, method, params):
                write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    message = json.loads(received.get(timeout=max(0.1, deadline - time.monotonic())))
                    if message.get("id") == request_id:
                        if "error" in message:
                            raise RuntimeError("Official MCP rejected " + method)
                        return message["result"]
                raise TimeoutError("Official MCP timed out: " + method)

            rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "blender-codex-smoke", "version": "0.1"}})
            write({"jsonrpc": "2.0", "method": "notifications/initialized"})
            tools = rpc(2, "tools/list", {})["tools"]
            names = {tool["name"] for tool in tools}
            required = {"execute_blender_code", "get_objects_summary", "get_screenshot_of_area_as_image"}
            assert required <= names, "Missing official connected-instance tools"
            result = rpc(3, "tools/call", {"name": "execute_blender_code", "arguments": {"code":
                "import bpy, os\nresult = {'process_id': os.getpid(), 'filepath': bpy.data.filepath, "
                "'objects': sorted(o.name for o in bpy.context.scene.objects)}"}})
            assert not result.get("isError"), "Official executor returned a tool error"
            payload = json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))
            assert payload["status"] == "ok", "Blender code execution failed"
            assert payload["result"]["process_id"] == blender_pid, "Wrong Blender process"
            assert payload["result"]["filepath"] == "", "Unexpected saved/user blend file"
            assert "Cube" in payload["result"]["objects"], "Factory scene missing"
            (runtime / "smoke-tools.json").write_text(json.dumps(tools, indent=2), encoding="utf-8")
            print("OFFICIAL_MCP_PASS: %d tools; connected execute_blender_code verified PID %d; "
                  "factory startup only; no model call or user file load/save" % (len(tools), blender_pid))
            mcp.stdin.close()
        finally:
            for process in reversed(processes):
                stop(process)


if __name__ == "__main__":
    main()
