import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("session_state_under_test", ROOT / "blender_codex/session_state.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=")


class SessionStateTests(unittest.TestCase):
    def setUp(self):
        self.state = module.SessionState()
        self.addCleanup(lambda: self.state.resources.close())

    def tool(self, item_id="item", phase="started", **updates):
        item = {"id": item_id, "type": "mcpToolCall", "tool": "execute_blender_code", "arguments": {"code": "import bpy"}, "status": "inProgress"}
        item.update(updates)
        return {"type": "tool", "phase": phase, "thread_id": "thread", "turn_id": "turn", "item_id": item_id, "item": item}

    def test_correlated_tools_keep_multiple_inputs_progress_results_and_errors(self):
        self.state.apply(self.tool())
        self.state.apply(self.tool("second"))
        self.state.apply({"type": "tool_progress", "thread_id": "thread", "turn_id": "turn", "item_id": "item", "text": "Working"})
        self.state.apply(self.tool(phase="completed", result={"content": [{"type": "text", "text": "actual result"}]}, status="completed"))
        self.state.apply(self.tool("second", "completed", error={"message": "tool failed"}, status="failed"))
        first, second = self.state.tool_calls
        self.assertEqual(json.loads(first["id"]), ["thread", "turn", "item"])
        self.assertEqual(first["progress"], ["Working"])
        self.assertEqual(first["input"], {"code": "import bpy"})
        self.assertEqual(first["content"][0]["text"], "actual result")
        self.assertEqual(second["status"], "failed")
        self.assertEqual(second["error"], {"message": "tool failed"})
        self.assertNotIn("parent_id", first)
        self.state.apply(self.tool())
        self.assertEqual(first["status"], "completed")

    def test_structured_official_error_is_failed_even_with_completed_transport_status(self):
        self.state.apply(self.tool(phase="completed", status="completed", error=None,
                                  result={"structuredContent": {"status": "error", "message": "PID guard aborted before mutation"}, "content": []}))
        row = self.state.tool_calls[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["error"], "PID guard aborted before mutation")

    def test_one_first_seen_sequence_orders_messages_and_tools_without_moving_updates(self):
        user = self.state.pending_user("Go", [])
        self.state.apply(self.tool())
        self.state.apply({"type": "delta", "thread_id": "thread", "turn_id": "turn", "item_id": "answer", "text": "Done"})
        tool = self.state.tool_calls[0]
        first_seq = tool["seq"]
        self.state.apply(self.tool(phase="completed", result={"content": []}))
        self.assertEqual(tool["seq"], first_seq)
        combined = sorted(self.state.messages + self.state.tool_calls, key=lambda entry: entry["seq"])
        self.assertEqual([row["id"] for row in combined], [user["id"], tool["id"], "answer"])

    def test_result_image_is_stable_authorized_resource_and_base64_not_in_snapshot(self):
        event = self.tool(phase="completed", result={"content": [{"type": "image", "mimeType": "image/png", "data": base64.b64encode(PNG).decode()}]})
        self.state.apply(event)
        first = self.state.artifacts[0]
        self.assertEqual(self.state.resources.get(first["id"])[2], PNG)
        self.state.apply(event)
        self.assertEqual(len(self.state.artifacts), 1)
        self.assertEqual(self.state.tool_calls[0]["resource_ids"], [first["id"]])
        self.assertNotIn(base64.b64encode(PNG).decode(), json.dumps(self.state.snapshot_fields()))
        self.assertEqual(self.state.tool_calls[0]["content"][0]["resource_id"], first["id"])

    def test_user_attachments_are_explicit_handles_and_become_image_or_text_inputs(self):
        image = self.state.resources.upload("view.png", "image/png", base64.b64encode(PNG).decode())
        text = self.state.resources.upload("notes.md", "text/markdown", base64.b64encode(b"read me").decode())
        self.state.attachments.extend([image, text])
        images, texts, handles = self.state.attachment_inputs()
        self.assertEqual(Path(images[0]).read_bytes(), PNG)
        self.assertIn("untrusted DATA", texts[0])
        self.assertEqual(handles, [image["id"], text["id"]])
        with self.assertRaises(ValueError):
            self.state.attachment_inputs(["C:/arbitrary/private.txt"])
        self.state.pending_user("Read these", handles)
        self.state.attachments.clear()
        self.assertEqual({a["id"] for a in self.state.artifacts}, set(handles))

    def test_embedded_resource_bytes_and_typed_project_file_link_materialize(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            output = project / "result.pdf"
            output.write_bytes(b"%PDF-1.7\nfixture output")
            self.state.project_root = directory
            content = [{"type": "resource", "resource": {"uri": "memory://result", "mimeType": "text/plain", "text": "embedded result"}},
                       {"type": "resource_link", "uri": output.as_uri(), "mimeType": "application/pdf", "name": "result.pdf"}]
            self.state.apply(self.tool(phase="completed", result={"content": content}))
            row = self.state.tool_calls[0]
            self.assertEqual(len(row["resource_ids"]), 2)
            self.assertEqual([self.state.resources.get(h)[2] for h in row["resource_ids"]], [b"embedded result", output.read_bytes()])
            self.assertTrue(all(block["type"] == "resource" and block.get("resource_id") for block in row["content"]))

    def test_authoritative_user_id_and_final_message_replace_stream_without_duplication(self):
        self.state.pending_user("Hello", [])
        self.state.apply({"type": "turn_accepted", "thread_id": "thread", "turn_id": "turn"})
        self.state.apply({"type": "user_item", "thread_id": "thread", "turn_id": "turn", "item_id": "actual-user-item"})
        self.assertEqual(self.state.messages[0]["id"], "actual-user-item")
        self.state.apply({"type": "delta", "thread_id": "thread", "turn_id": "turn", "item_id": "agent-item", "text": "partial"})
        self.state.apply({"type": "message_final", "thread_id": "thread", "turn_id": "turn", "item_id": "agent-item", "text": "complete authoritative text"})
        self.assertEqual(len(self.state.messages), 2)
        self.assertEqual(self.state.messages[-1]["text"], "complete authoritative text")

    def test_upload_validation_and_limits_do_not_expose_paths_or_active_html(self):
        for name, mime, data in (("../private.txt", "text/plain", b"bad"), ("active.html", "text/html", b"<script>bad</script>"),
                                  ("file.pdf", "application/pdf", b"%PDF-1.7"), ("wrong.png", "image/png", b"bad image")):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.state.resources.upload(name, mime, base64.b64encode(data).decode())
        with self.assertRaises(ValueError):
            self.state.resources.upload("x.txt", "text/plain", "not base64!")
        self.state.resources.MAX_FILE = 2
        with self.assertRaises(ValueError):
            self.state.resources.add("x.txt", "text/plain", b"long")

    def test_output_files_require_explicit_destination_inside_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            inside, outside = project / "output.txt", root / "private.txt"
            inside.write_text("generated output")
            outside.write_text("private")
            self.state.project_root = str(project)
            self.state.apply(self.tool("inside", "completed", arguments={"output_path": str(inside)}, result={"content": []}))
            self.state.apply(self.tool("outside", "completed", arguments={"output_path": str(outside)}, result={"content": []}))
            self.state.apply(self.tool("untrusted-result", "completed", result={"path": str(outside), "url": outside.as_uri()}))
            self.assertEqual(len(self.state.artifacts), 1)
            self.assertEqual(self.state.resources.get(self.state.artifacts[0]["id"])[2], b"generated output")
            self.assertFalse(self.state.tool_calls[1]["resource_ids"])
            self.assertFalse(self.state.tool_calls[2]["resource_ids"])

    def test_pending_submission_acceptance_and_correlated_messages(self):
        row = self.state.pending_user("Hello", [])
        self.assertTrue(row["pending"])
        self.state.apply({"type": "turn_accepted", "thread_id": "thread", "turn_id": "turn"})
        self.assertFalse(row["pending"])
        self.assertEqual(row["turn_id"], "turn")
        for item, text in (("a", "First"), ("b", "Second"), ("a", " part")):
            self.state.apply({"type": "delta", "thread_id": "thread", "turn_id": "turn", "item_id": item, "text": text})
        self.assertEqual([m["text"] for m in self.state.messages], ["Hello", "First part", "Second"])
        self.assertEqual([m["id"] for m in self.state.messages[1:]], ["a", "b"])

    def test_stop_and_close_mark_unfinished_tools_without_success(self):
        self.state.apply(self.tool())
        self.state.apply({"type": "done", "turn_id": "turn", "status": "interrupted"})
        self.assertEqual(self.state.tool_calls[0]["status"], "interrupted")
        self.state.pending_user("Not accepted", [])
        self.state.apply({"type": "closed"})
        self.assertIn("error", self.state.messages[-1])
        self.assertFalse(self.state.snapshot_fields()["history_supported"])

    def test_new_chat_revokes_old_resource_handles(self):
        resource = self.state.resources.add("note.txt", "text/plain", b"old resource")
        self.state.reset_history()
        with self.assertRaises(KeyError):
            self.state.resources.get(resource["id"])


if __name__ == "__main__":
    unittest.main()
