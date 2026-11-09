"""Opt-in live/CLI isolation proof using only a dedicated factory-startup scene.

Requires the prepared official runtime. No Codex/model call or user scene used.
The temporary .blend and its synchronized copies are owned by this test.
"""
import argparse
import hashlib
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
spec = importlib.util.spec_from_file_location("executor_backend", ROOT / "blender_codex/official_backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


def drain(stream, output):
    for line in iter(stream.readline, b""):
        output.put(line.decode("utf-8", "replace"))


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    for pipe in (process.stdin, process.stdout, process.stderr):
        if pipe is not None:
            pipe.close()


def source_hashes(source):
    names = ("LICENSE", "mcp/blmcp/tools/execute_blender_code.py", "mcp/blmcp/tools_helpers/blender_cli.py",
             "addon/blender_mcp_addon/mcp_to_blender_server.py")
    return {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default=r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime/deepblick-executor-receipt.json")
    args = parser.parse_args()
    command, launch_args = backend.resolve_launch()
    runtime = backend.DEFAULT_RUNTIME_ROOT
    source = runtime / "source"
    before = source_hashes(source)
    receipt = {"passed": False, "phase": "starting", "source_revision": backend.SOURCE_REVISION,
               "source_license": backend.SOURCE_LICENSE, "source_sha256": before, "model_call": False}

    def record(phase, **values):
        receipt.update(phase=phase, **values)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print("EXECUTOR_PHASE", phase, flush=True)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    processes = []
    with tempfile.TemporaryDirectory(prefix="executor-isolation-", dir=runtime) as directory:
        folder = Path(directory)
        isolated_environment = dict(os.environ)
        for key, suffix in (("BLENDER_USER_CONFIG", "config"), ("BLENDER_USER_SCRIPTS", "scripts"),
                            ("BLENDER_USER_EXTENSIONS", "extensions"), ("BLENDER_USER_DATAFILES", "datafiles")):
            isolated_path = folder / suffix
            isolated_path.mkdir()
            isolated_environment[key] = str(isolated_path)
        blend = folder / "factory.blend"
        bootstrap = folder / "bootstrap.py"
        bootstrap.write_text(
            "import sys, os, bpy\n"
            + "sys.path.insert(0, %r)\n" % str(source / "addon")
            + "from blender_mcp_addon import mcp_to_blender_server, execute_blocking\n"
            + "bpy.ops.wm.save_as_mainfile(filepath=%r)\n" % str(blend)
            + "bpy.data.objects['Cube'].scale.z = 1.5\nbpy.context.view_layer.update()\n"
            + "mcp_to_blender_server.start('127.0.0.1', %d)\n" % port
            + "print('EXECUTOR_READY', os.getpid(), flush=True)\n"
            + "try:\n    execute_blocking.run()\nfinally:\n    mcp_to_blender_server.stop()\n",
            encoding="utf-8")
        try:
            live = subprocess.Popen([args.blender, "--background", "--factory-startup", "--online-mode",
                                     "--python", str(bootstrap)], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags,
                                    env=isolated_environment)
            processes.append(live)
            output = queue.Queue()
            threading.Thread(target=drain, args=(live.stdout, output), daemon=True).start()
            deadline = time.monotonic() + 45
            while True:
                line = output.get(timeout=max(.1, deadline - time.monotonic()))
                if line.startswith("EXECUTOR_READY"):
                    live_pid = int(line.split()[-1])
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("Factory Blender failed to start")
            record("factory_ready", live_pid=live_pid)
            env = dict(isolated_environment, BLENDER_MCP_HOST="127.0.0.1", BLENDER_MCP_PORT=str(port), BLENDER_PATH=args.blender)
            mcp = subprocess.Popen([command, *launch_args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env, creationflags=flags)
            processes.append(mcp)
            received, errors = queue.Queue(), queue.Queue()
            threading.Thread(target=drain, args=(mcp.stdout, received), daemon=True).start()
            threading.Thread(target=drain, args=(mcp.stderr, errors), daemon=True).start()

            def write(message):
                mcp.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
                mcp.stdin.flush()

            counter = 0

            def rpc(method, params, timeout=150):
                nonlocal counter
                counter += 1
                request_id = counter
                write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
                end = time.monotonic() + timeout
                while True:
                    message = json.loads(received.get(timeout=max(.1, end - time.monotonic())))
                    if message.get("id") == request_id:
                        if "error" in message:
                            raise RuntimeError("Official MCP RPC failed: " + method)
                        return message["result"]
                    if "id" in message and "method" in message:
                        raise RuntimeError("Unexpected server request in executor test: " + message["method"])

            def tool(name, code, **arguments):
                value = rpc("tools/call", {"name": name, "arguments": dict(arguments, code=code)})
                if value.get("isError"):
                    raise AssertionError("Tool failed: " + json.dumps(value))
                return json.loads(next(block["text"] for block in value["content"] if block["type"] == "text"))

            rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "deepblick-executor-isolation", "version": "1"}})
            write({"jsonrpc": "2.0", "method": "notifications/initialized"})
            tools = rpc("tools/list", {})["tools"]
            assert {"execute_blender_code", "execute_blender_code_for_cli"} <= {t["name"] for t in tools}
            guard = "import bpy, os\nassert os.getpid() == %r\nassert bpy.data.filepath == %r\n" % (live_pid, str(blend))
            live_changed = tool("execute_blender_code", guard
                                + "obj=bpy.data.objects['Cube']\nobj.scale.z *= 2\nbpy.context.view_layer.update()\n"
                                + "result={'pid':os.getpid(),'height':obj.dimensions.z,'dirty_before_save':bpy.data.is_dirty}\n"
                                + "bpy.ops.wm.save_as_mainfile(filepath=%r)\n" % str(blend))
            assert live_changed["status"] == "ok", live_changed
            assert abs(live_changed["result"]["height"] - 6.0) < 1e-5
            record("live_changed_cli_starting", live_result=live_changed["result"])
            cli_changed = tool("execute_blender_code_for_cli",
                               "import bpy, os\nassert os.getpid() != %r\n" % live_pid
                               + "assert os.path.dirname(bpy.data.filepath) == %r\n" % str(folder)
                               + "obj=bpy.data.objects['Cube']\nbefore=obj.dimensions.z\nobj.scale.z *= 2\nbpy.context.view_layer.update()\n"
                               + "result={'pid':os.getpid(),'height_before':before,'height_after':obj.dimensions.z}\n",
                               blend_file=str(blend))
            assert cli_changed["pid"] != live_pid
            assert abs(cli_changed["height_before"] - 6.0) < 1e-5, cli_changed
            assert abs(cli_changed["height_after"] - 12.0) < 1e-5, cli_changed
            record("cli_changed_live_recheck", cli_result=cli_changed)
            live_after = tool("execute_blender_code", guard
                              + "result={'pid':os.getpid(),'height':bpy.data.objects['Cube'].dimensions.z}\n")
            assert live_after["result"]["pid"] == live_pid
            assert abs(live_after["result"]["height"] - 6.0) < 1e-5
            assert not list(folder.glob("*_mcp_*.blend")), "Synced temporary copy was not cleaned up"
            after = source_hashes(source)
            assert before == after, "Official source changed during execution"
            record("complete", passed=True, tool_count=len(tools), live_after_cli=live_after["result"],
                   scope="dedicated factory-startup process; test-owned blend and isolated user config",
                   no_test_copy_left=True, stable_official_source=True)
            print("OFFICIAL_EXECUTOR_ISOLATION_PASS: live height 3->6 (explicit test-file save); separate CLI 6->12; live remains 6")
        except Exception as exc:
            record("failed", failed_phase=receipt["phase"], error=str(exc),
                   stable_official_source=source_hashes(source) == before)
            raise
        finally:
            for process in reversed(processes):
                stop(process)


if __name__ == "__main__":
    main()
