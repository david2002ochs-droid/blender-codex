"""Official summary notifications -> real client -> state; no model/Blender process.

--export writes deterministic protocol-replay snapshots for the production browser test.
All summary strings in this test are explicitly fixtures, never product content.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("thinking_test_" + name, ROOT / "blender_codex" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


State = load("session_state").SessionState
Client = load("codex_client").CodexClient
bounded_state = load("state_projection").bounded_state


class Replay:
    def __init__(self):
        self.state = State()
        self.events = []
        self.client = Client(self.events.append)
        self.client._thread_id = "fixture-thread"
        self.client._busy = self.state.busy = self.state.ready = True
        self.state.thread_id = "fixture-thread"
        self.state.pending_user("Protocol replay: inspect the Blender selection", [])
        self.notify("item/started", item={"type": "userMessage", "id": "fixture-user", "content": []})

    def notify(self, method, **params):
        payload = {"threadId": "fixture-thread", "turnId": "fixture-turn", **params}
        self.client._notification(method, payload)
        events = list(self.events)
        self.events.clear()
        for event in events:
            self.state.apply(event)
            if event["type"] == "done":
                self.state.busy = False

    def start(self, item="fixture-reasoning"):
        self.notify("item/started", item={"type": "reasoning", "id": item, "summary": [], "content": ["PRIVATE_SENTINEL"]})

    def delta(self, text, index=0, item="fixture-reasoning"):
        self.notify("item/reasoning/summaryTextDelta", itemId=item, summaryIndex=index, delta=text)

    def finish_item(self, summary=None):
        self.notify("item/completed", item={"type": "reasoning", "id": "fixture-reasoning", "summary": summary or [], "content": ["PRIVATE_SENTINEL"]})

    def finish(self, status="completed"):
        self.notify("turn/completed", turn={"id": "fixture-turn", "status": status, "items": [],
                    "startedAt": 1794048000, "completedAt": 1794048003, "durationMs": 3210})

    def snapshot(self):
        return copy.deepcopy(dict(self.state.snapshot_fields(), messages=self.state.messages, busy=self.state.busy,
                                  ready=True, status="Connected", error="", activity="", context={}, settings={}, approvals=[]))

    def close(self):
        self.state.resources.close()


class ReasoningTests(unittest.TestCase):
    def setUp(self):
        self.replay = Replay()
        self.addCleanup(self.replay.close)

    def test_local_official_schema_contract(self):
        schema = ROOT / "protocol/codex_app_server_protocol.v2.schemas.json"
        if not schema.is_file():
            self.skipTest("Installed Codex protocol schema is required for this contract check")
        definitions = json.loads(schema.read_text(encoding="utf-8"))["definitions"]
        delta = definitions["ReasoningSummaryTextDeltaNotification"]
        self.assertEqual(set(delta["required"]), {"threadId", "turnId", "itemId", "summaryIndex", "delta"})
        self.assertEqual(definitions["ReasoningSummaryPartAddedNotification"]["properties"]["summaryIndex"]["type"], "integer")
        item = next(x for x in definitions["ThreadItem"]["oneOf"] if x["properties"].get("type", {}).get("enum") == ["reasoning"])
        self.assertEqual(item["properties"]["summary"]["items"]["type"], "string")
        self.assertIn("summary", definitions["TurnStartParams"]["properties"])

    def test_turn_requests_public_auto_summary(self):
        client = self.replay.client
        with patch.object(client, "_request") as request:
            client._begin_turn("test", "{}", 0, [], [])
        self.assertEqual(request.call_args.args[1]["summary"], "auto")

    def test_summary_parts_stream_completion_and_replay_are_one_row(self):
        r = self.replay
        r.start()
        r.notify("item/reasoning/summaryPartAdded", itemId="fixture-reasoning", summaryIndex=1)
        r.delta("Second public paragraph", 1)
        r.delta("First public paragraph", 0)
        r.notify("item/reasoning/summaryPartAdded", itemId="fixture-reasoning", summaryIndex=0)
        self.assertEqual(r.state.reasoning[0]["text"], "First public paragraph\n\nSecond public paragraph")
        seq = r.state.reasoning[0]["seq"]
        r.finish_item(["Authoritative final summary"])
        r.finish_item(["Authoritative final summary"])
        r.start()
        r.delta("late delta")
        self.assertEqual(len(r.state.reasoning), 1)
        self.assertEqual(r.state.reasoning[0]["seq"], seq)
        self.assertEqual(r.state.reasoning[0]["text"], "Authoritative final summary")
        r.finish()
        r.delta("after completed turn")
        self.assertEqual(r.state.reasoning[0]["status"], "completed")
        self.assertEqual(r.state.reasoning[0]["duration_ms"], 3210)

    def test_raw_reasoning_wrong_turn_and_plan_never_become_summary(self):
        r = self.replay
        r.start()
        r.notify("item/reasoning/textDelta", itemId="fixture-reasoning", contentIndex=0, delta="PRIVATE_SENTINEL")
        r.notify("item/reasoning/summaryTextDelta", itemId="wrong", summaryIndex=0, delta="wrong thread", threadId="other")
        r.notify("item/reasoning/summaryTextDelta", itemId="wrong", summaryIndex=0, delta="wrong turn", turnId="other")
        r.notify("item/started", item={"type": "plan", "id": "plan", "text": "not reasoning"})
        r.finish_item()
        self.assertEqual(r.state.reasoning[0]["text"], "")
        self.assertEqual(r.state.tool_calls, [])
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(r.snapshot()))
        self.assertEqual(len(r.state.reasoning), 1)

    def test_final_turn_readback_replaces_stream_by_identity(self):
        r = self.replay
        r.start()
        r.delta("Partial")
        r.notify("turn/completed", turn={"id": "fixture-turn", "status": "completed", "items": [
            {"type": "reasoning", "id": "fixture-reasoning", "summary": ["Final public summary"], "content": ["PRIVATE_SENTINEL"]}]})
        self.assertEqual(len(r.state.reasoning), 1)
        self.assertEqual(r.state.reasoning[0]["text"], "Final public summary")
        self.assertEqual(r.state.reasoning[0]["turn_status"], "completed")

    def test_close_does_not_change_prior_completed_or_other_turn(self):
        r = self.replay
        r.start()
        r.delta("Earlier summary")
        r.finish()
        r.state.apply({"type": "reasoning", "phase": "delta", "thread_id": "fixture-thread", "turn_id": "next-turn", "item_id": "next-item", "summary_index": 0, "text": "Later summary"})
        r.state.apply({"type": "done", "thread_id": "another-thread", "turn_id": "next-turn", "status": "failed"})
        self.assertEqual(r.state.reasoning[1]["status"], "running")
        r.state.apply({"type": "closed"})
        self.assertEqual([row["status"] for row in r.state.reasoning], ["completed", "interrupted"])

    def test_failure_interrupt_closed_and_fatal_stop_animation(self):
        for status in ("completed", "failed", "interrupted", "closed", "fatal"):
            with self.subTest(status=status):
                r = Replay()
                try:
                    r.start()
                    r.delta("Partial public summary")
                    if status in ("closed", "fatal"):
                        r.state.apply({"type": "closed"} if status == "closed" else {"type": "error", "fatal": True})
                    else:
                        r.finish(status)
                    expected = {"closed": "interrupted", "fatal": "failed"}.get(status, status)
                    self.assertEqual(r.state.reasoning[0]["status"], expected)
                    self.assertEqual(r.state.reasoning[0]["turn_status"], expected)
                    self.assertEqual(r.state.reasoning[0]["text"], "Partial public summary")
                finally:
                    r.close()

    def test_history_cache_resume_identity_and_order(self):
        r = self.replay
        r.start()
        r.delta("Cached public summary")
        r.finish_item()
        r.finish()
        projection = r.state.history_projection()
        r.state.restore_projection(projection, [])
        self.assertEqual(r.state.reasoning[0]["text"], "Cached public summary")
        turns = [{"id": "fixture-turn", "status": "completed", "items": [
            {"type": "userMessage", "id": "fixture-user", "content": [{"type": "text", "text": "User"}]},
            {"type": "reasoning", "id": "fixture-reasoning", "summary": ["History public summary"], "content": ["PRIVATE_SENTINEL"]},
            {"type": "agentMessage", "id": "fixture-answer", "text": "Answer"}]}]
        for _ in range(2):
            r.state.hydrate("fixture-thread", turns)
            self.assertEqual(len(r.state.reasoning), 1)
            self.assertEqual(r.state.reasoning[0]["text"], "History public summary")
            rows = sorted(r.state.messages + r.state.reasoning, key=lambda x: x["seq"])
            self.assertEqual([x["item_id"] for x in rows], ["fixture-user", "fixture-reasoning", "fixture-answer"])
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(r.snapshot()))

    def test_large_unicode_payloads_sparse_indices_and_global_budget(self):
        r = self.replay
        r.start()
        for index in (-1, 32, 10**18, True, "0"):
            r.delta("invalid", index)
        self.assertEqual(r.state.reasoning[0]["text"], "")
        for number in range(100):
            r.delta("🧊" * 100000, item="large-" + str(number))
        self.assertLessEqual(len(r.state.reasoning), 64)
        self.assertLessEqual(sum(len(x["text"]) for x in r.state.reasoning), State.REASONING_TOTAL_LIMIT)
        self.assertTrue(any(x["truncated"] for x in r.state.reasoning))
        self.assertGreater(r.state.reasoning_omitted, 0)
        self.assertLess(len(json.dumps(r.snapshot()).encode()), 2 * 1024 * 1024)
        view = bounded_state(r.snapshot(), r.state.resources, 4 * 1024 * 1024 - 65536)
        self.assertLess(len(json.dumps(view).encode()), 4 * 1024 * 1024)
        r.finish()
        self.assertEqual(r.state._reasoning_parts, {})

    def test_history_large_payload_is_bounded_and_missing_summary_stays_empty(self):
        r = self.replay
        r.state.hydrate("fixture-thread", [{"id": "turn-large", "status": "interrupted", "items": [
            {"type": "reasoning", "id": "large", "summary": ["A" * 6000000]},
            {"type": "reasoning", "id": "empty", "content": ["PRIVATE_SENTINEL"]}]}])
        self.assertEqual(len(r.state.reasoning[0]["text"]), State.REASONING_ITEM_LIMIT)
        self.assertTrue(r.state.reasoning[0]["truncated"])
        self.assertEqual(r.state.reasoning[1]["text"], "")
        self.assertLess(len(json.dumps(r.snapshot())), 40000)


def export_snapshots(destination):
    r = Replay()
    states = {}
    try:
        r.start()
        states["empty_running"] = r.snapshot()
        r.delta("**Inspecting the selection**\n")
        states["streaming"] = r.snapshot()
        r.delta("Public summary replay: checking object bounds.\n\n**Preparing the response**\n")
        states["streaming_next"] = r.snapshot()
        r.finish_item(["**Inspecting the selection**\nPublic summary replay: checking object bounds.", "**Preparing the response**\nSummary complete."])
        r.notify("item/completed", item={"id": "fixture-answer", "type": "agentMessage", "text": "Fixture response: the selection is ready."})
        r.finish()
        states["completed"] = r.snapshot()
        projection = r.state.history_projection()
        r.state.restore_projection(projection, [])
        r.state.thread_id = "fixture-thread"
        states["restored"] = r.snapshot()
        for status in ("failed", "interrupted"):
            stopped = Replay()
            try:
                stopped.start()
                stopped.delta("Public summary replay: work stopped before the final response.")
                stopped.finish(status)
                states[status] = stopped.snapshot()
            finally:
                stopped.close()
        r.state.hydrate("fixture-thread", [{"id": "fixture-turn", "status": "completed", "items": [
            {"type": "userMessage", "id": "fixture-user", "content": [{"type": "text", "text": "Protocol replay: inspect the Blender selection"}]},
            {"type": "reasoning", "id": "fixture-reasoning", "summary": ["History public summary"]},
            {"type": "agentMessage", "id": "fixture-answer", "text": "Fixture response: the selection is ready."}]}])
        states["history"] = r.snapshot()
        r.state.hydrate("fixture-thread", [{"id": "fixture-turn", "status": "completed", "items": [
            {"type": "reasoning", "id": "fixture-reasoning", "summary": []}]}])
        # A fresh state has no cached summary to carry forward.
        r.state.reset_history()
        r.state.hydrate("fixture-thread", [{"id": "fixture-turn", "status": "completed", "items": [
            {"type": "reasoning", "id": "fixture-reasoning", "summary": []}]}])
        states["empty_completed"] = r.snapshot()
        r.state.hydrate("fixture-thread", [{"id": "fixture-turn", "status": "completed", "items": [
            {"type": "reasoning", "id": "fixture-reasoning", "summary": ["Large preview\n" + "Bounded public fixture. " * 50000]}]}])
        states["large"] = r.snapshot()
        Path(destination).write_text(json.dumps({"evidence": "protocol replay through real CodexClient and SessionState; no live model", "states": states}, indent=2), encoding="utf-8")
    finally:
        r.close()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--export":
        export_snapshots(sys.argv[2])
    else:
        unittest.main()
