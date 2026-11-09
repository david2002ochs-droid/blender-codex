"""Headless Blender wiring/worker smoke; no user scene, model turn or provider call."""
from pathlib import Path
import sys
import threading
from unittest.mock import patch

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import blender_codex
from blender_codex import codex_client, blender_target

instances = []
class Client:
    def __init__(self, callback, native_tools=None):
        self.native_tools = native_tools
        instances.append(self)
    def start(self, **kwargs):
        self.options = kwargs
    def close(self):
        pass

before = set(bpy.data.objects)
addon_utils.enable("blender_codex", default_set=True)
try:
    # The official endpoint has its own integration checks; this smoke isolates
    # native-tool wiring and deliberately starts no Blender MCP listener.
    with patch.object(codex_client, "CodexClient", Client), patch.object(
            blender_target, "target_environment", return_value={
                "BLENDER_MCP_HOST": "127.0.0.1", "BLENDER_MCP_PORT": "19876"}):
        assert bpy.ops.codex_chat.connect() == {"FINISHED"}
    runner = instances[-1].native_tools
    assert runner.specs[0]["name"] == "hi3d_image_to_3d"
    assert Path(runner.python).is_file()
    runner.credentials = ("", "")
    result = runner.call("hi3d_image_to_3d", {"task_id": "existing-test-job"}, threading.Event())
    assert result["success"] is False and result["stage"] == "config", result
    assert set(bpy.data.objects) == before
    assert not bpy.data.filepath
    print("NATIVE_BLENDER_PASS: main-thread registration, bundled Python worker, structured config failure, scene unchanged")
finally:
    addon_utils.disable("blender_codex", default_set=True)
