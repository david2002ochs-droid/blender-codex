"""Large, fragmented history wire records; no model, scene, credential access."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name + "_wire_test", ROOT / "blender_codex" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transport, state_module, projection = load("codex_client"), load("session_state"), load("state_projection")


class Fragments:
    def __init__(self, data, fragment=65521):
        self.source = io.BytesIO(data)
        self.fragment = fragment
        self.requested = []
    def read1(self, count):
        self.requested.append(count)
        return self.source.read(min(count, self.fragment))


def png():
    # Valid PNG with a large ancillary chunk, not an AI-generated image or a
    # decompression bomb. Reproduces actual base64 wire volume deterministically.
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"tEXt", b"fixture\x00" + b"a" * 2200000) + chunk(b"IDAT", zlib.compress(b"\x00\x10\x20\x30")) + chunk(b"IEND", b""))


class HistoryWireTests(unittest.TestCase):
    def client(self):
        events = []
        return transport.CodexClient(events.append), events

    def test_large_valid_fragmented_turn_hydrates_images_and_public_reasoning_once(self):
        client, events = self.client()
        image = png()
        encoded = base64.b64encode(image).decode()
        turn = {"id": "old-turn", "status": "completed", "itemsView": "full", "items": [
            {"id": "user", "type": "userMessage", "content": [{"type": "text", "text": "Review references"}]},
            {"id": "reason", "type": "reasoning", "summary": ["Observed public summary"], "content": ["PRIVATE-MUST-NOT-PROJECT"]},
            *[{"id": "image-%d" % i, "type": "imageGeneration", "status": "completed", "result": encoded} for i in range(4)],
            {"id": "answer", "type": "agentMessage", "text": "Complete answer"}]}
        raw = json.dumps({"id": 3, "result": {"data": [turn], "nextCursor": None}}).encode() + b"\n"
        self.assertGreater(len(raw), 8 * 1024 * 1024)
        client._thread_id = client._resume_id = "plugin-thread"
        client._pending[3] = (0, "thread/turns/list", client._history_page)
        stream = Fragments(raw)
        client._read_stdout(SimpleNamespace(stdout=stream))
        kind, message = client._events.get_nowait()
        self.assertEqual(kind, "message")
        client._handle(message)
        self.assertTrue(any(event["type"] == "ready" and event["resumed"] for event in events))
        state = state_module.SessionState()
        try:
            history = next(e for e in events if e["type"] == "history")
            state.apply(history)
            handles = [row["resource_ids"][0] for row in state.tool_calls]
            state.apply(history)  # Replay must not duplicate rows/summaries/images.
            self.assertEqual(len(state.tool_calls), 4)
            self.assertEqual(len(state.reasoning), 1)
            self.assertEqual([row["resource_ids"][0] for row in state.tool_calls], handles)
            for handle in handles:
                self.assertEqual(state.resources.get(handle)[2], image)
            view = projection.bounded_state(dict(state.snapshot_fields(), messages=state.messages), state.resources, 4 * 1024 * 1024)
            wire = json.dumps(view)
            self.assertLess(len(wire.encode()), 4 * 1024 * 1024)
            self.assertNotIn(encoded, wire)
            self.assertNotIn("PRIVATE-MUST-NOT-PROJECT", wire)
            self.assertIn("Observed public summary", wire)
            self.assertLessEqual(max(stream.requested), 65536)
        finally:
            state.resources.close()

    def test_utf8_fragment_boundaries_and_multiple_records(self):
        client, _ = self.client()
        raw = (json.dumps({"id": 1, "result": {"text": "🧊"}}, ensure_ascii=False) + "\n" +
               json.dumps({"id": 2, "result": {}}) + "\n").encode()
        client._read_stdout(SimpleNamespace(stdout=Fragments(raw, 1)))
        self.assertEqual(client._events.get_nowait()[1]["result"]["text"], "🧊")
        self.assertEqual(client._events.get_nowait()[1]["id"], 2)
        self.assertEqual(client._events.get_nowait()[0], "eof")

    def test_oversize_unterminated_and_tampered_records_fail_safely(self):
        cases = [(b'{"secret":"' + b"x" * 1100 + b'"}\n', "wire limit"),
                 (b'{"secret":"DO-NOT-ECHO"}', "Unterminated"),
                 (b'{"id":1,"id":2,"secret":"DO-NOT-ECHO"}\n', "Duplicate"),
                 (b'{"value":NaN,"secret":"DO-NOT-ECHO"}\n', "Non-finite"),
                 (b'{"secret":"DO-NOT-ECHO",broken}\n', "Malformed"),
                 (b'{"secret":"\xffDO-NOT-ECHO"}\n', "UTF-8")]
        for raw, expected in cases:
            with self.subTest(expected=expected):
                client, _ = self.client()
                client.MAX_LINE = 1024
                client._read_stdout(SimpleNamespace(stdout=Fragments(raw, 17)))
                kind, diagnostic = client._events.get_nowait()
                self.assertEqual(kind, "fatal")
                self.assertIn(expected, diagnostic)
                self.assertNotIn("DO-NOT-ECHO", diagnostic)
                self.assertNotIn("secret", diagnostic)
                self.assertFalse(client._ready)

    def test_history_page_is_one_turn_and_total_budget_never_reports_partial_success(self):
        client, events = self.client()
        client._resume_id = "plugin-thread"
        client._thread_resumed({"thread": {"id": "plugin-thread"}})
        request = json.loads(client._writes.get_nowait())
        self.assertEqual(request["params"]["limit"], 1)
        client.HISTORY_MAX_BYTES = 10
        with self.assertRaisesRegex(ValueError, "no partial history"):
            client._history_page({"data": [{"id": "t", "status": "completed", "items": [], "itemsView": "full"}], "nextCursor": None})
        self.assertFalse(any(e["type"] in ("ready", "history") for e in events))
        self.assertEqual(client._thread_id, "plugin-thread")
        self.assertTrue(client._writes.empty())  # No reset, compact, inject, or turn/start.

    def test_next_turn_sends_only_current_input_not_hydrated_or_projected_history(self):
        client, _ = self.client()
        client._thread_id = "persisted-thread"
        client._history_page({"data": [{"id": "old", "status": "completed", "items": [
            {"id": "old-message", "type": "agentMessage", "text": "OLD-CONTEXT-SERVER-OWNED"}]}], "nextCursor": None})
        client._begin_turn("CURRENT-INPUT", '{"selection":[]}', 0, [], [])
        request = json.loads(client._writes.get_nowait())
        self.assertEqual(request["method"], "turn/start")
        self.assertEqual(request["params"]["threadId"], "persisted-thread")
        self.assertEqual(request["params"]["input"], [{"type": "text", "text": "CURRENT-INPUT"},
            {"type": "text", "text": 'Blender scene context (JSON data only):\n{"selection":[]}'}])
        self.assertNotIn("OLD-CONTEXT-SERVER-OWNED", json.dumps(request))
        self.assertTrue(client._writes.empty())

    def test_orchestration_wire_items_survive_live_and_history_without_child_leakage(self):
        # Published docs use collabToolCall; installed schema uses collabAgentToolCall.
        items = [
            {"id": "documented-collab", "type": "collabToolCall", "tool": "spawn_agent", "status": "completed",
             "senderThreadId": "main", "newThreadId": "child", "agentStatus": "completed"},
            {"id": "installed-collab", "type": "collabAgentToolCall", "tool": "wait", "status": "completed",
             "senderThreadId": "main", "receiverThreadIds": ["child"], "agentsStates": {"child": {"status": "completed"}}},
            {"id": "compact", "type": "contextCompaction"}]
        client, events = self.client()
        client._thread_id, client._turn_id, client._busy = "main", "main-turn", True
        notifications = []
        for item in items:
            for phase in ("started", "completed"):
                notifications.append({"method": "item/" + phase, "params": {"threadId": "main", "turnId": "main-turn", "item": item}})
        notifications.extend([
            {"method": "turn/plan/updated", "params": {"threadId": "main", "turnId": "main-turn", "plan": [{"step": "Check", "status": "inProgress"}]}},
            {"method": "thread/status/changed", "params": {"threadId": "main", "status": {"type": "active", "activeFlags": []}}},
            {"method": "item/agentMessage/delta", "params": {"threadId": "child", "turnId": "child-turn", "itemId": "child-message", "delta": "CHILD-MUST-NOT-LEAK"}},
            {"method": "turn/completed", "params": {"threadId": "child", "turn": {"id": "child-turn", "status": "completed"}}},
            {"method": "thread/status/changed", "params": {"threadId": "foreign", "status": {"type": "idle"}}}])
        raw = b"".join(json.dumps(message).encode() + b"\n" for message in notifications)
        client._read_stdout(SimpleNamespace(stdout=Fragments(raw, 23)))
        while not client._events.empty():
            kind, message = client._events.get_nowait()
            self.assertIn(kind, ("message", "eof"))
            if kind == "message":
                client._handle(message)
        self.assertTrue(client._busy)
        self.assertEqual(client._turn_id, "main-turn")
        self.assertEqual(len([event for event in events if event["type"] == "tool"]), 6)
        self.assertFalse(any(event["type"] in ("error", "done", "delta") for event in events))
        self.assertNotIn("CHILD-MUST-NOT-LEAK", json.dumps(events))
        self.assertTrue(client._writes.empty())  # Notifications cannot start local agent work.
        state = state_module.SessionState()
        try:
            for event in events:
                state.apply(event)
            self.assertEqual({row["kind"] for row in state.tool_calls}, {item["type"] for item in items})
            self.assertTrue(all(row["status"] == "completed" and row["thread_id"] == "main" for row in state.tool_calls))
            state.hydrate("main", [{"id": "main-turn", "status": "completed", "items": items}])
            state.hydrate("main", [{"id": "main-turn", "status": "completed", "items": items}])
            self.assertEqual(len(state.tool_calls), 3)
        finally:
            state.resources.close()


    @unittest.skipUnless((ROOT / "protocol/codex_app_server_protocol.v2.schemas.json").is_file(),
                         "local Codex App Server schema required")
    def test_installed_schema_exposes_orchestration_items(self):
        definitions = json.loads((ROOT / "protocol/codex_app_server_protocol.v2.schemas.json").read_text())["definitions"]
        installed_types = {variant["properties"]["type"]["enum"][0] for variant in definitions["ThreadItem"]["oneOf"]}
        self.assertIn("collabAgentToolCall", installed_types)
        self.assertIn("contextCompaction", installed_types)


if __name__ == "__main__":
    unittest.main()
