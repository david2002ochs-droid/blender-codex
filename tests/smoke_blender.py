"""Run with Blender --background --factory-startup --python this_file.

Exercises real bpy registration, selection context and UI operators, using a
fake transport. This is not an end-to-end Codex/MCP test.
"""
from pathlib import Path
import json
import sys

import addon_utils
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import blender_codex as addon
from blender_codex.context import collect_context


class FakeClient:
    def __init__(self):
        self.sent = []
        self.approvals = []
        self.stopped = False
        self.closed = False

    def send(self, text, context):
        self.sent.append((text, context))

    def interrupt(self):
        self.stopped = True

    def approve(self, request_id, approved):
        self.approvals.append((request_id, approved))

    def close(self):
        self.closed = True


addon_utils.enable("blender_codex", default_set=True)
try:
    assert "blender_codex" in bpy.context.preferences.addons
    assert hasattr(bpy.types.WindowManager, "codex_chat")
    assert addon._on_load_pre in bpy.app.handlers.load_pre
    cube = bpy.data.objects["Cube"]
    bpy.ops.object.select_all(action="DESELECT")
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    cube.scale.z = 1.5
    bpy.context.view_layer.update()
    snapshot = collect_context(bpy.context)
    assert snapshot["active_object"]["name"] == "Cube"
    assert snapshot["active_object"]["dimensions"][2] == 3.0
    assert snapshot["filepath"] == ""
    json.dumps(snapshot, allow_nan=False)

    fake = FakeClient()
    addon._session.client = fake
    addon._session.ready = True
    bpy.context.window_manager.codex_chat.input_text = "What is selected?"
    assert bpy.ops.codex_chat.send() == {"FINISHED"}
    assert fake.sent[0][1]["active_object"]["dimensions"][2] == 3.0
    assert addon._session.busy
    assert not addon.CODEX_OT_send.poll(bpy.context)

    generation = addon._session.generation
    for event in (
        {"type": "delta", "text": "Selected: "},
        {"type": "delta", "text": "Cube"},
        {"type": "approval", "request_id": "approval-1", "text": "Allow operation?"},
    ):
        addon._session.events.put((generation, event))
    addon._drain_events()
    assert addon._session.messages[-1]["text"] == "Selected: Cube"
    addon._handle_event({"type": "activity", "text": "Retrying"})
    assert addon._session.busy and addon.CODEX_OT_stop.poll(bpy.context)
    addon._handle_event({"type": "approval", "request_id": "resolved", "text": "Already handled"})
    addon._handle_event({"type": "approval_resolved", "request_id": "resolved"})
    assert [item["request_id"] for item in addon._session.approvals] == ["approval-1"]
    assert bpy.ops.codex_chat.approve(approved=False) == {"FINISHED"}
    assert fake.approvals == [("approval-1", False)]
    assert bpy.ops.codex_chat.stop() == {"FINISHED"}
    assert fake.stopped
    addon._session.events.put((generation, {"type": "done"}))
    addon._drain_events()
    assert not addon._session.busy

    # The web bridge calls exactly these main-thread actions. Validate live
    # context and stale approval protection through the actual adapter.
    from blender_codex import web_ui
    result = web_ui._action({"action": "send", "text": "Inspect the cube", "include_view": False}, bpy.context)
    assert result == {"ok": True}
    assert fake.sent[-1][1]["active_object"]["dimensions"][2] == 3.0
    assert web_ui._snapshot(bpy.context)["context"]["active_object"]["name"] == "Cube"
    addon._session.approvals.append({"request_id": "current", "text": "Current request"})
    try:
        web_ui._action({"action": "approve", "request_id": "stale", "approved": True}, bpy.context)
        raise AssertionError("A stale approval must not authorize the current action")
    except ValueError:
        pass
    assert len(addon._session.approvals) == 1
    assert web_ui._action({"action": "approve", "request_id": "current", "approved": False}, bpy.context) == {"ok": True}
    assert fake.approvals[-1] == ("current", False)

    addon._on_load_pre(None)
    assert fake.closed
    assert addon._session.client is None
    assert not addon._session.messages
    addon._session.events.put((generation, {"type": "delta", "text": "stale"}))
    addon._drain_events()
    assert not addon._session.messages
    print("BLENDER_ADDON_SMOKE_PASS: registration, live context, send, streaming, approval, stop, file reset")
finally:
    addon_utils.disable("blender_codex", default_set=True)
    assert not hasattr(bpy.types.WindowManager, "codex_chat")
    assert addon._on_load_pre not in bpy.app.handlers.load_pre
