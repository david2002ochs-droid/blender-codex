import base64
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name + "_history_test", ROOT / "blender_codex" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


history_module, state_module = load("chat_history"), load("session_state")


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.history = history_module.ChatHistory(self.root)
        self.state = state_module.SessionState()
        self.addCleanup(lambda: self.state.resources.close())

    def test_only_plugin_registered_ids_can_list_open_save_or_rename(self):
        self.history.register("plugin-thread", "project")
        self.assertEqual([x["id"] for x in self.history.threads()], ["plugin-thread"])
        for action in (lambda: self.history.load("desktop-cli-thread"), lambda: self.history.rename("desktop-cli-thread", "No"),
                       lambda: self.history.save("desktop-cli-thread", {}, [])):
            with self.assertRaises(ValueError):
                action()

    def test_index_survives_recreation_and_concurrent_plugin_instances(self):
        second = history_module.ChatHistory(self.root)
        self.history.register("a")
        second.register("b")
        second.rename("a", "Saved name")
        records = history_module.ChatHistory(self.root).threads()
        self.assertEqual({x["id"] for x in records}, {"a", "b"})
        self.assertEqual(self.history.title("a"), "Saved name")

    def test_snapshot_restores_registered_bytes_and_exact_capability_handles(self):
        self.history.register("thread")
        descriptor = self.state.resources.add("note.txt", "text/plain", b"immutable bytes")
        self.state.artifacts.append(descriptor)
        self.state.pending_user("Read file", [descriptor["id"]])
        self.state.apply({"type": "turn_accepted", "thread_id": "thread", "turn_id": "turn"})
        self.history.save("thread", self.state.history_projection(), self.state.resources.export())
        projection, resources, missing = history_module.ChatHistory(self.root).load("thread")
        self.assertFalse(missing)
        restored = state_module.SessionState()
        self.addCleanup(lambda: restored.resources.close())
        restored.restore_projection(projection, resources)
        self.assertEqual(restored.messages[0]["resource_ids"], [descriptor["id"]])
        self.assertEqual(restored.resources.get(descriptor["id"])[2], b"immutable bytes")

    def test_missing_or_tampered_resource_is_not_recovered_from_arbitrary_paths(self):
        self.history.register("thread")
        descriptor = self.state.resources.add("note.txt", "text/plain", b"cached bytes")
        self.history.save("thread", {}, self.state.resources.export())
        path = self.history._folder("thread") / "resources" / descriptor["id"]
        path.write_bytes(b"tampered")
        _, resources, missing = self.history.load("thread")
        self.assertFalse(resources)
        self.assertEqual(missing, [descriptor["id"]])

    def test_authoritative_hydration_replaces_stale_text_and_preserves_cached_image_handles(self):
        descriptor = self.state.resources.add("tool-image.png", "image/png", b"\x89PNG\r\n\x1a\nfixture")
        self.state.artifacts.append(descriptor)
        self.state.messages = [{"id": "a", "item_id": "a", "turn_id": "turn", "role": "Codex", "text": "stale", "seq": 1}]
        self.state.tool_calls = [{"id": '["thread","turn","tool"]', "thread_id": "thread", "turn_id": "turn", "item_id": "tool", "status": "completed",
                                  "result": {"content": [{"type": "image", "resource_id": descriptor["id"]}]}, "content": [{"type": "image", "resource_id": descriptor["id"]}],
                                  "resource_ids": [descriptor["id"]], "seq": 2}]
        self.state.hydrate("thread", [{"id": "turn", "status": "completed", "items": [
            {"id": "a", "type": "agentMessage", "text": "authoritative text"},
            {"id": "tool", "type": "mcpToolCall", "tool": "get_screenshot_of_area_as_image", "arguments": {}, "result": None, "status": "completed"}]}])
        self.assertEqual(self.state.messages[0]["text"], "authoritative text")
        self.assertEqual(self.state.tool_calls[0]["resource_ids"], [descriptor["id"]])
        self.assertEqual(self.state.tool_calls[0]["history_source"], "plugin-cache")

    def test_resource_restore_keeps_image_handle_when_server_replays_same_bytes(self):
        png = b"\x89PNG\r\n\x1a\nfixture"
        original = self.state.resources.add("tool-image.png", "image/png", png)
        self.history.register("thread")
        self.history.save("thread", {}, self.state.resources.export())
        projection, resources, missing = self.history.load("thread")
        self.state.restore_projection(projection, resources)
        self.state.apply({"type": "tool", "phase": "completed", "thread_id": "thread", "turn_id": "turn", "item_id": "tool",
                          "item": {"id": "tool", "type": "mcpToolCall", "tool": "image", "arguments": {}, "result": {"content": [
                              {"type": "image", "mimeType": "image/png", "data": base64.b64encode(png).decode()}]}}})
        self.assertEqual(self.state.tool_calls[0]["resource_ids"], [original["id"]])

    def test_history_never_rereads_changed_old_output_paths(self):
        project = self.root / "project"
        project.mkdir()
        output = project / "generated.txt"
        output.write_text("old generated output")
        self.state.project_root = str(project)
        item = {"id": "file-tool", "type": "mcpToolCall", "tool": "render_viewport_to_path", "status": "completed",
                "arguments": {"output_path": str(output)}, "result": {"content": []}}
        self.state.apply({"type": "tool", "phase": "completed", "thread_id": "thread", "turn_id": "turn", "item_id": "file-tool", "item": item})
        handle = self.state.tool_calls[0]["resource_ids"][0]
        output.write_text("different current file; never historical data")
        self.state.hydrate("thread", [{"id": "turn", "status": "completed", "items": [item]}])
        self.assertEqual(self.state.tool_calls[0]["resource_ids"], [handle])
        self.assertEqual(self.state.resources.get(handle)[2], b"old generated output")
        self.assertEqual(len(self.state.resources.export()), 1)

    def test_cached_structured_error_is_still_an_error_after_history_resume(self):
        self.state.tool_calls = [{"id": '["thread","turn","tool"]', "thread_id": "thread", "turn_id": "turn", "item_id": "tool", "status": "completed",
                                  "result": {"structuredContent": {"status": "error", "message": "Actual old execution failed"}}, "content": [], "resource_ids": [], "seq": 1}]
        self.state.hydrate("thread", [{"id": "turn", "status": "completed", "items": [
            {"id": "tool", "type": "mcpToolCall", "tool": "execute_blender_code", "arguments": {}, "status": "completed", "result": None}]}])
        self.assertEqual(self.state.tool_calls[0]["status"], "failed")
        self.assertEqual(self.state.tool_calls[0]["error"], "Actual old execution failed")
