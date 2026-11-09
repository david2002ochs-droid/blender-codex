import base64
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name + "_projection_test", ROOT / "blender_codex" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


state_module, projection = load("session_state"), load("state_projection")


class StateSizeTests(unittest.TestCase):
    def setUp(self):
        self.state = state_module.SessionState()
        self.addCleanup(lambda: self.state.resources.close())

    def test_actual_image_generation_base64_field_is_resource_not_duplicated_text(self):
        # A >2 MiB image payload reproduces the real >4 MiB duplicated snapshot.
        image = b"\x89PNG\r\n\x1a\n" + b"fixture" * 330000
        encoded = base64.b64encode(image).decode()
        self.assertGreater(len(encoded) * 2, 4 * 1024 * 1024)
        self.state.apply({"type": "tool", "phase": "completed", "thread_id": "thread", "turn_id": "turn", "item_id": "image",
                          "item": {"id": "image", "type": "imageGeneration", "status": "completed", "result": encoded}})
        row = self.state.tool_calls[0]
        self.assertEqual(row["content"][0]["type"], "image")
        handle = row["resource_ids"][0]
        self.assertEqual(self.state.resources.get(handle)[2], image)
        snapshot = dict(self.state.snapshot_fields(), messages=self.state.messages)
        self.assertLess(len(json.dumps(snapshot).encode()), 20000)
        self.assertNotIn(encoded, json.dumps(snapshot))

    def test_legacy_history_image_cache_is_upgraded_without_changing_user_history(self):
        image = b"\x89PNG\r\n\x1a\n" + b"fixture" * 330000
        encoded = base64.b64encode(image).decode()
        legacy = {"tool_calls": [{"id": '["thread","turn","image"]', "thread_id": "thread", "turn_id": "turn", "item_id": "image", "seq": 1,
                                  "kind": "imageGeneration", "name": "imageGeneration", "status": "completed", "result": encoded,
                                  "content": [{"type": "text", "text": encoded}], "resource_ids": []}], "messages": [], "artifacts": []}
        self.state.restore_projection(legacy, [])
        row = self.state.tool_calls[0]
        self.assertEqual(self.state.resources.get(row["resource_ids"][0])[2], image)
        self.assertLess(len(json.dumps(self.state.history_projection()).encode()), 20000)
        self.assertEqual(legacy["tool_calls"][0]["result"], encoded)

    def test_generic_six_mib_result_is_bounded_with_authorized_full_detail(self):
        text = "observed output " * 180000
        row = {"id": "actual-tool-id", "seq": 2, "status": "completed", "result": text, "content": [{"type": "text", "text": text}], "resource_ids": []}
        original = {"ready": True, "busy": False, "tool_calls": [row], "messages": [], "artifacts": []}
        self.assertGreater(len(json.dumps(original).encode()), 4 * 1024 * 1024)
        view = projection.bounded_state(original, self.state.resources, 4 * 1024 * 1024)
        self.assertLessEqual(len(json.dumps(view).encode()), 4 * 1024 * 1024)
        self.assertTrue(view["ready"])
        self.assertTrue(view["state_projection"]["truncated"])
        handle = view["tool_calls"][0]["projection"]["detail_resource_id"]
        self.assertEqual(json.loads(self.state.resources.get(handle)[2])["result"], text)
        again = projection.bounded_state(original, self.state.resources, 4 * 1024 * 1024)
        self.assertEqual(again["tool_calls"][0]["projection"]["detail_resource_id"], handle)
        self.assertEqual(original["tool_calls"][0]["result"], text)

    def test_large_transcript_window_is_bounded_and_does_not_overwrite_history(self):
        messages = [{"id": "item-%d" % i, "seq": i, "role": "Codex", "text": "x" * 20000} for i in range(300)]
        original = {"ready": True, "busy": False, "messages": messages, "tool_calls": [], "artifacts": []}
        view = projection.bounded_state(original, self.state.resources, 4 * 1024 * 1024)
        self.assertLessEqual(len(json.dumps(view).encode()), 4 * 1024 * 1024)
        self.assertGreater(view["state_projection"]["omitted_messages"], 0)
        self.assertEqual(view["messages"][-1]["id"], "item-299")
        self.assertEqual(len(original["messages"]), 300)

    def test_full_resource_cache_cannot_turn_snapshot_overflow_into_exception(self):
        self.state.resources.MAX_TOTAL = 1
        text = "x" * 3000000
        original = {"ready": True, "tool_calls": [{"id": "tool", "status": "completed", "result": text, "content": [{"type": "text", "text": text}]}], "messages": [], "artifacts": []}
        view = projection.bounded_state(original, self.state.resources, 4 * 1024 * 1024)
        self.assertLessEqual(len(json.dumps(view).encode()), 4 * 1024 * 1024)
        self.assertTrue(view["ready"])
        self.assertTrue(view["state_projection"]["warnings"])


if __name__ == "__main__":
    unittest.main()
