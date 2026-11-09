"""Real official executor/load-handler fence in one dedicated factory Blender.

No Codex/model call, user .blend load/save, or running preview is accessed.
"""
import importlib.util
from pathlib import Path
import sys
import os

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get("BLENDER_CODEX_MCP_ADDON_ROOT", str(ROOT / ".runtime/official-mcp/source/addon")))
from blender_mcp_addon import mcp_to_blender_server as server

spec = importlib.util.spec_from_file_location("scene_guard_native_test", ROOT / "blender_codex/scene_lifecycle.py")
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)
original = server._execute_code
assert bpy.app.background and not bpy.data.filepath
server.start("127.0.0.1", 0)
try:
    lifecycle.install({"blender_mcp_addon": None})
    lifecycle.register(bpy)
    old = lifecycle.bind_turn(bpy.context)
    before = server._execute_code("import bpy\nbpy.context.scene['old_scene_marker'] = True\nresult = {'old': True}\n", True)
    assert before.response["status"] == "ok", before.response
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    assert not bpy.data.filepath
    assert "old_scene_marker" not in bpy.context.scene
    blocked = server._execute_code("import bpy\nbpy.context.scene['unexpected_old_write'] = True\nresult = {}\n", True)
    assert blocked.response["code"] == "scene_target_changed", blocked.response
    assert "unexpected_old_write" not in bpy.context.scene
    new = lifecycle.bind_turn(bpy.context)
    assert new["scene_epoch"] != old["scene_epoch"]
    allowed = server._execute_code("import bpy\nbpy.context.scene['new_scene_marker'] = True\nresult = {'new': True}\n", True)
    assert allowed.response["status"] == "ok", allowed.response
    assert bpy.context.scene["new_scene_marker"] is True
    print("NATIVE_SCENE_FENCE_PASS: actual load hooks kept listener; old unsaved-scene code rejected; fresh bound turn executed; no model/user file")
finally:
    lifecycle.unregister()
    assert server._execute_code is original
    server.stop()
