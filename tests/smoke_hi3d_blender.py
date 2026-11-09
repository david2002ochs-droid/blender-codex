"""Real Blender GLB roundtrip and Hi3D UI lifecycle; no external API calls."""
import json
from pathlib import Path
import sys
import tempfile
import time

import addon_utils
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import blender_codex
from blender_codex import hi3d_ui, hi3d

addon_utils.enable("blender_codex", default_set=True)
try:
    with tempfile.TemporaryDirectory(prefix="hi3d_smoke_") as tmp:
        root = Path(tmp)
        hi3d_ui._record_path = str(root / "job.json")
        state = bpy.context.window_manager.hi3d_settings
        state.client_id = "fake-client-for-test"
        state.client_secret = "fake-secret-for-test"
        state.output_directory = str(root)

        cube = bpy.data.objects["Cube"]
        bpy.ops.object.select_all(action="DESELECT")
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        glb = root / "fixture.glb"
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True)
        assert glb.read_bytes()[:4] == b"glTF"

        class FakeProvider:
            queries = 0

            def __init__(self, client_id, client_secret):
                pass

            def balance(self):
                return 123.0

            def query(self, task_id):
                self.__class__.queries += 1
                return {"state": "success", "task_id": task_id, "url": "https://example.com/fixture.glb"}

            def download(self, url, destination):
                Path(destination).write_bytes(glb.read_bytes())
                return destination

            def submit(self, *args, **kwargs):
                raise AssertionError("Smoke test must never submit a paid task")

        original = hi3d.Hi3DClient
        hi3d.Hi3DClient = FakeProvider
        try:
            def drain_until_done():
                deadline = time.monotonic() + 5
                while hi3d_ui._busy() and time.monotonic() < deadline:
                    hi3d_ui._drain()
                    time.sleep(0.01)
                hi3d_ui._drain()
                assert not hi3d_ui._busy(), "Worker did not finish"
                assert not hi3d_ui._error, hi3d_ui._error

            assert bpy.ops.hi3d.access() == {"FINISHED"}
            drain_until_done()
            assert hi3d_ui._balance == "123.0"
            state.task_id = "smoke-existing-job"
            assert bpy.ops.hi3d.resume() == {"FINISHED"}
            drain_until_done()
            assert FakeProvider.queries == 1
            assert hi3d_ui._record["state"] == "success"
            saved = Path(hi3d_ui._record_path).read_text()
            assert "fake-secret-for-test" not in saved
            assert "fake-client-for-test" not in saved
            assert "https://" not in saved
            assert json.loads(saved)["task_id"] == "smoke-existing-job"
            before = set(bpy.data.objects)
            assert bpy.ops.hi3d.import_glb() == {"FINISHED"}
            imported = set(bpy.data.objects) - before
            assert imported and any(obj.type == "MESH" for obj in imported)
            assert all(obj.get("hi3d_task_id") == "smoke-existing-job" for obj in imported)

            # Session credentials must not leak into a saved blend file.
            blend = root / "credentials-check.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=False)
            data = blend.read_bytes()
            assert b"fake-secret-for-test" not in data
            assert b"fake-client-for-test" not in data
            hi3d_ui._load_pre(None)
            assert state.client_id == "" and state.client_secret == ""
            hi3d_ui._load_post(None)
            assert state.task_id == "smoke-existing-job"
            print("HI3D_BLENDER_SMOKE_PASS: balance, resume, GLB download/import, provenance, job persistence, credentials not saved")
        finally:
            hi3d.Hi3DClient = original
finally:
    addon_utils.disable("blender_codex", default_set=True)
    assert not hasattr(bpy.types.WindowManager, "hi3d_settings")
