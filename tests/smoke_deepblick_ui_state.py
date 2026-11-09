"""Run in factory-startup Blender; no network/model call, scene edit, or save."""
import base64
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy

history_directory = tempfile.TemporaryDirectory(prefix="history-state-smoke-", dir=ROOT / ".runtime")
previous_history = os.environ.get("BLENDER_CODEX_HISTORY_DIR")
os.environ["BLENDER_CODEX_HISTORY_DIR"] = history_directory.name

bpy.ops.preferences.addon_enable(module="blender_codex")
import blender_codex as addon
from blender_codex import web_ui
from blender_codex.codex_client import CodexClient

try:
    session = addon._session
    client = CodexClient(lambda event: addon._handle_event(event))
    client.models = [{"id": "fixture-model-id", "model": "fixture-provider-model", "displayName": "Fixture model",
                      "supportedReasoningEfforts": [{"reasoningEffort": "high"}], "defaultReasoningEffort": "high"}]
    client.selected_model = "fixture-model-id"
    client._ready = True
    session.client = client
    session.ready = True
    session.models = client.models
    web_ui._action({"action": "select_model", "model_id": "fixture-model-id", "reasoning_effort": "high"}, bpy.context)
    web_ui._action({"action": "set_permission_mode", "permission_mode": "read_only"}, bpy.context)
    assert client.permission_mode == "read_only"
    resource = web_ui._action({"action": "upload_attachment", "name": "notes.md", "mime_type": "text/markdown",
                              "data_base64": base64.b64encode(b"fixture notes").decode()}, bpy.context)["attachment"]
    snapshot = web_ui._snapshot(bpy.context)
    assert snapshot["markup_active"] is False
    assert web_ui._action({"action": "markup_cancel"}, bpy.context) == {"ok": True, "canceled": False}
    assert snapshot["attachments"][0]["id"] == resource["id"]
    assert snapshot["selected_model"] == "fixture-model-id"
    assert snapshot["reasoning_effort"] == "high"
    assert snapshot["permission_mode"] == "read_only"
    assert snapshot["history_supported"] is True
    session.history_store.register("fixture-history", "factory-startup", "Stored fixture")
    assert web_ui._action({"action": "threads/list"}, bpy.context)["threads"][0]["id"] == "fixture-history"
    assert web_ui._action({"action": "threads/rename", "thread_id": "fixture-history", "title": "Renamed fixture"}, bpy.context)["scope"] == "plugin-index"
    web_ui._action({"action": "send", "text": "Read attachment", "attachment_ids": [resource["id"]]}, bpy.context)
    command, data = client._events.get_nowait()
    assert command == "send"
    assert "fixture notes" in data[-1][0]
    assert session.busy and session.messages[-1]["pending"]
    try:
        web_ui._action({"action": "threads/open", "thread_id": "fixture-history"}, bpy.context)
    except ValueError:
        pass
    else:
        raise AssertionError("Busy history switch was not rejected")
    addon._handle_event({"type": "turn_accepted", "thread_id": "fixture-thread", "turn_id": "fixture-turn"})
    assert not session.messages[-1]["pending"]
    addon._handle_event({"type": "done", "turn_id": "fixture-turn", "status": "interrupted"})
    assert not session.busy
    session.apply({"type": "tool", "phase": "started", "thread_id": "fixture-thread", "turn_id": "fixture-turn-2",
                   "item_id": "fixture-tool", "item": {"id": "fixture-tool", "type": "mcpToolCall", "tool": "fixture", "arguments": {}}})
    addon._disconnect()
    assert session.tool_calls[-1]["status"] == "interrupted"
    try:
        web_ui._action({"action": "threads/open", "thread_id": "arbitrary-desktop-thread"}, bpy.context)
    except ValueError:
        pass
    else:
        raise AssertionError("Unindexed desktop/CLI thread was accepted")
    session.events.put((session.generation - 1, {"type": "message", "text": "STALE-EVENT"}))
    addon._drain_events()
    assert not any(message.get("text") == "STALE-EVENT" for message in session.messages)
    assert bpy.data.filepath == ""
    assert set(bpy.data.objects)  # Factory objects remain, untouched.
    print("DEEPBLICK_BLENDER_STATE_PASS: actual main-thread action/snapshot adapter; fixture catalog only; no model or scene edit")
finally:
    bpy.ops.preferences.addon_disable(module="blender_codex")
    history_directory.cleanup()
    if previous_history is None:
        os.environ.pop("BLENDER_CODEX_HISTORY_DIR", None)
    else:
        os.environ["BLENDER_CODEX_HISTORY_DIR"] = previous_history
