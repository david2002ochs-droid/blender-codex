"""Codex-schema events -> real adapter projection and outbound wire parameters.

Offline contract checks. They prove no live model/image-generation behavior;
run only against an agreed immutable snapshot using integration_snapshot.py.
"""
import base64
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "blender_codex" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transport = load("integration_codex", "codex_client.py")
projection = load("integration_projection", "session_state.py")


def pixel_png():
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\xff")) + chunk(b"IEND", b"")


class AdapterIntegration(unittest.TestCase):
    def setUp(self):
        self.state = projection.SessionState()
        self.addCleanup(self.state.resources.close)
        self.events = []

        def callback(event):
            self.events.append(event)
            self.state.apply(event)
        self.client = transport.CodexClient(callback)
        self.client._thread_id = "actual-thread"
        self.client._turn_id = "actual-turn"
        self.client._busy = True

    def notify(self, method, **values):
        self.client._notification(method, dict(threadId="actual-thread", turnId="actual-turn", **values))

    def test_stream_multiple_calls_results_errors_and_image_bytes(self):
        self.notify("item/agentMessage/delta", itemId="message-1", delta="Hello ")
        self.notify("item/agentMessage/delta", itemId="message-1", delta="Blender")
        for item_id, failed in (("tool-1", False), ("tool-2", True)):
            item = {"id": item_id, "type": "mcpToolCall", "server": "blender", "tool": "execute_blender_code",
                    "arguments": {"code": "result = {'fixture': True}"}, "status": "inProgress"}
            self.notify("item/started", item=item)
            self.notify("item/mcpToolCall/progress", itemId=item_id, message="fixture progress")
            item = dict(item, status="failed" if failed else "completed",
                        error={"message": "fixture execution failure"} if failed else None,
                        result={"content": [{"type": "text", "text": "original result"},
                                            {"type": "image", "mimeType": "image/png", "data": base64.b64encode(pixel_png()).decode()}]})
            self.notify("item/completed", item=item)
        self.notify("item/completed", item={"id": "message-1", "type": "agentMessage", "text": "Hello Blender"})
        self.assertEqual([row["text"] for row in self.state.messages], ["Hello Blender"])
        self.assertEqual([row["item_id"] for row in self.state.tool_calls], ["tool-1", "tool-2"])
        self.assertEqual([row["status"] for row in self.state.tool_calls], ["completed", "failed"])
        self.assertEqual(self.state.tool_calls[0]["arguments"]["code"], "result = {'fixture': True}")
        self.assertEqual(self.state.tool_calls[0]["content"][0]["text"], "original result")
        handle = self.state.tool_calls[0]["resource_ids"][0]
        descriptor, _path, data = self.state.resources.get(handle)
        self.assertEqual(data, pixel_png())
        self.assertEqual(descriptor["mime_type"], "image/png")
        self.assertNotIn('"data":', json.dumps(self.state.tool_calls))

    def test_actual_catalog_selection_and_wire_parameters(self):
        self.client._busy = False
        catalog = [{"id": "catalog-id", "model": "wire-model", "displayName": "Fixture model",
                    "isDefault": True, "inputModalities": ["text", "image"],
                    "supportedReasoningEfforts": [{"reasoningEffort": "high", "description": "Fixture"}],
                    "defaultReasoningEffort": "high"}]
        self.client._models({"data": catalog, "nextCursor": None}, str(ROOT))
        thread = json.loads(self.client._writes.get_nowait())
        self.assertEqual(thread["method"], "thread/start")
        self.assertEqual(thread["params"]["model"], "wire-model")
        self.assertEqual(thread["params"]["developerInstructions"], (ROOT / "blender_codex/instructions.txt").read_text(encoding="utf-8").strip())
        self.client.configure(model="catalog-id", reasoning_effort="high", permission_mode="read_only")
        self.client._begin_turn("fixture", "{}", 1, [], [])
        turn = json.loads(self.client._writes.get_nowait())
        self.assertEqual(turn["method"], "turn/start")
        self.assertEqual(turn["params"]["model"], "wire-model")
        self.assertEqual(turn["params"]["effort"], "high")
        self.assertEqual(turn["params"]["approvalPolicy"], "on-request")
        self.assertEqual(turn["params"]["sandboxPolicy"]["type"], "readOnly")

    def test_explicit_uploaded_image_reaches_local_image_wire_input(self):
        desc = self.state.resources.upload("input.png", "image/png", base64.b64encode(pixel_png()).decode())
        self.state.attachments.append(desc)
        images, texts, handles = self.state.attachment_inputs([desc["id"]])
        self.assertEqual(handles, [desc["id"]])
        image_inputs = self.client._local_images(images)
        self.client._begin_turn("fixture", "{}", 1, image_inputs, texts)
        request = json.loads(self.client._writes.get_nowait())
        attachments = [item for item in request["params"]["input"] if item["type"] == "localImage"]
        self.assertEqual(len(attachments), 1)
        self.assertEqual(Path(attachments[0]["path"]).read_bytes(), pixel_png())

    def test_decline_resolved_and_interrupt_emit_real_rpc_ids(self):
        self.client._server_request(123, "item/commandExecution/requestApproval", {
            "threadId": "actual-thread", "turnId": "actual-turn", "itemId": "tool-1", "command": "fixture"})
        self.assertEqual(self.state.approvals[0]["request_id"], 123)
        self.client._answer_approval(123, False)
        answer = json.loads(self.client._writes.get_nowait())
        self.assertEqual(answer, {"id": 123, "result": {"decision": "decline"}})
        self.client._interrupt_pending = True
        self.client._try_interrupt()
        request = json.loads(self.client._writes.get_nowait())
        self.assertEqual(request["method"], "turn/interrupt")
        self.assertEqual(request["params"], {"threadId": "actual-thread", "turnId": "actual-turn"})

    def test_file_output_is_registered_only_inside_project(self):
        with tempfile.TemporaryDirectory() as directory:
            self.state.project_root = directory
            output = Path(directory) / "fixture.png"
            output.write_bytes(pixel_png())
            self.notify("item/completed", item={"id": "render-1", "type": "mcpToolCall", "server": "blender",
                        "tool": "render_viewport_to_path", "arguments": {"output_path": str(output)},
                        "status": "completed", "error": None, "result": {"content": [{"type": "text", "text": "fixture render complete"}]}})
            self.assertEqual(len(self.state.artifacts), 1)
            descriptor, _path, data = self.state.resources.get(self.state.artifacts[0]["id"])
            self.assertEqual(descriptor["name"], "fixture.png")
            self.assertEqual(data, output.read_bytes())

    def test_reconnect_limit_is_explicit_and_resources_cannot_survive_reset(self):
        desc = self.state.resources.upload("input.txt", "text/plain", base64.b64encode(b"fixture").decode())
        self.assertFalse(self.state.snapshot_fields()["history_supported"])
        self.state.reset_history()
        with self.assertRaises(KeyError):
            self.state.resources.get(desc["id"])


if __name__ == "__main__":
    unittest.main()
