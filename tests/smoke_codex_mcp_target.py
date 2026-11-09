"""Read-only real app-server -> official MCP target proof; no model turn.

Only runs execute_blender_code with os.getpid(). It never reads/changes scene
data, loads/saves a file, or requests model generation/provider credits.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import threading

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("target_smoke_backend", ROOT / "blender_codex/official_backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--expected-pid", required=True, type=int)
    parser.add_argument("--codex", default="codex")
    options = parser.parse_args()
    command, arguments = backend.resolve_launch()
    args = [options.codex, "app-server"]
    settings = {"command": command, "args": arguments, "enabled": True, "required": True,
                "env.BLENDER_MCP_HOST": "127.0.0.1", "env.BLENDER_MCP_PORT": str(options.port)}
    for name, value in settings.items():
        args.extend(["-c", "mcp_servers.blender." + name + "=" + json.dumps(value)])
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    received = queue.Queue()

    def read():
        try:
            for line in process.stdout:
                received.put(json.loads(line))
        finally:
            received.put({"closed": True})

    threading.Thread(target=read, daemon=True).start()

    def send(message):
        process.stdin.write((json.dumps(message) + "\n").encode())
        process.stdin.flush()

    def rpc(identity, method, params):
        send({"id": identity, "method": method, "params": params})
        while True:
            message = received.get(timeout=60)
            if message.get("closed"):
                raise RuntimeError("App-server closed before target verification")
            if message.get("id") == identity:
                if "error" in message:
                    raise RuntimeError(method + " failed: " + str(message["error"].get("message", "unknown error")))
                return message["result"]

    try:
        rpc(1, "initialize", {"clientInfo": {"name": "blender_codex_target_smoke", "version": "0.1"}, "capabilities": {"experimentalApi": True}})
        send({"method": "initialized", "params": {}})
        thread = rpc(2, "thread/start", {"cwd": str(ROOT), "approvalPolicy": "never", "sandbox": "danger-full-access", "ephemeral": True})["thread"]["id"]
        result = rpc(3, "mcpServer/tool/call", {"threadId": thread, "server": "blender", "tool": "execute_blender_code",
                    "arguments": {"code": "import os\nresult = {'process_id': os.getpid()}"}})
        # Version-matched response wraps the actual MCP result when necessary.
        payload = result.get("result", result)
        structured = payload.get("structuredContent")
        if structured is None:
            structured = json.loads(next(block["text"] for block in payload["content"] if block["type"] == "text"))
        actual = structured["result"]["process_id"]
        if actual != options.expected_pid:
            raise AssertionError("Wrong Blender process: expected %d, got %d" % (options.expected_pid, actual))
        print("CODEX_MCP_TARGET_PASS: expected=%d actual=%d port=%d; no scene/model operation" % (options.expected_pid, actual, options.port))
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=3)


if __name__ == "__main__":
    main()
