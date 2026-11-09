"""Native registration, lifecycle and provider readback. No paid/API calls."""
import importlib.util
import io
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender_codex"))
import hi3d_tool as tool
import native_tools
from test_hi3d import FakeHTTPS, glb, PNG, BASE, TOKEN, SECRET, URL

spec = importlib.util.spec_from_file_location("native_transport_test", ROOT / "blender_codex/codex_client.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


class ProviderToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / "input.png"
        self.image.write_bytes(PNG)
        self.payload = {"arguments": {"image_path": str(self.image)}, "credentials": ["test-client", SECRET],
                        "cwd": str(self.root), "output_dir": str(self.root / "models"),
                        "record_path": str(self.root / "jobs/job.json")}
        self.client = tool.ToolClient(*self.payload["credentials"])
        self.peer = FakeHTTPS()
        self.client._api = urllib.request.build_opener(self.peer)
        self.client._downloads = urllib.request.build_opener(self.peer)
        self.peer.add("POST", BASE + "/auth/token", {"accessToken": TOKEN})

    def execute(self):
        result = tool.execute(self.payload, lambda *_: self.client, sleep=lambda _: None)
        self.assertFalse(self.peer.steps)
        return result

    def success(self, resume=False):
        if not resume:
            self.peer.add("POST", BASE + "/submit-task", {"task_id": "existing-1"})
        self.peer.add("GET", BASE + "/query-task?task_id=existing-1", {"state": "success", "url": URL})
        self.peer.add("GET", URL, raw=glb())

    def test_downloaded_file_has_readback_and_is_not_reported_imported(self):
        self.success()
        result = self.execute()
        self.assertTrue(result["success"])
        self.assertEqual(result["task_id"], "existing-1")
        self.assertEqual(Path(result["model_path"]).read_bytes(), glb())
        self.assertEqual(result["readback"]["file"]["bytes"], len(glb()))
        self.assertEqual(len(result["readback"]["file"]["sha256"]), 64)
        self.assertFalse(result["readback"]["blender_imported"])
        journal = json.loads(Path(self.payload["record_path"]).read_text())
        self.assertEqual(journal["state"], "downloaded")
        self.assertNotIn(SECRET, json.dumps(journal))

    def test_resume_uses_no_submit_even_with_missing_image(self):
        self.payload["arguments"] = {"task_id": "existing-1", "image_path": "missing.png"}
        self.success(resume=True)
        self.assertTrue(self.execute()["success"])
        self.assertFalse(any(r.full_url.endswith("submit-task") for r in self.peer.requests))

    def test_original_error_envelope_is_preserved_with_secret_redaction(self):
        self.peer.add("POST", BASE + "/submit-task", raw=json.dumps({"code": 30010000,
            "msg": "balance is not enough " + SECRET + " " + TOKEN, "data": {"accessToken": "other-secret"}}).encode())
        result = self.execute()
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "submit")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["api_response"]["code"], 30010000)
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertNotIn("other-secret", json.dumps(result))
        self.assertEqual(len(self.peer.requests), 2)

    def test_task_id_is_durable_before_polling(self):
        self.peer.add("POST", BASE + "/submit-task", {"task_id": "existing-1"})
        def interrupted_poll(task_id):
            record = json.loads(Path(self.payload["record_path"]).read_text())
            self.assertEqual(record["task_id"], task_id)
            self.assertEqual(record["state"], "accepted")
            raise KeyboardInterrupt()
        self.client.query = interrupted_poll
        with self.assertRaises(KeyboardInterrupt):
            self.execute()
        result = native_tools.NativeTools._interrupted(Path(self.payload["record_path"]), {}, cancelled=True)
        self.assertEqual(result["task_id"], "existing-1")
        self.assertTrue(result["generation_may_be_billable"])

    def test_submit_401_preserves_error_and_never_retries_paid_request(self):
        self.peer.add("POST", BASE + "/submit-task", status=401,
                      raw=json.dumps({"code": 401, "msg": "expired", "data": {}}).encode())
        result = self.execute()
        self.assertFalse(result["success"])
        self.assertEqual(result["http_status"], 401)
        self.assertEqual(result["api_response"]["code"], 401)
        self.assertEqual(len(self.peer.requests), 2)

    def test_master_submits_documented_five_million_faces(self):
        self.payload["arguments"]["quality"] = "master"
        self.success()
        self.assertTrue(self.execute()["success"])
        body = self.peer.requests[1].data
        self.assertIn(b'"face"\r\n\r\n5000000', body)
        self.assertIn(b'"resolution"\r\n\r\n2048master', body)

    def test_invalid_download_never_reports_success(self):
        self.peer.add("POST", BASE + "/submit-task", {"task_id": "existing-1"})
        self.peer.add("GET", BASE + "/query-task?task_id=existing-1", {"state": "success", "url": URL})
        self.peer.add("GET", URL, raw=b"<html>error</html>")
        result = self.execute()
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "download")
        self.assertEqual(result["task_id"], "existing-1")


class WorkerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runner = native_tools.NativeTools(self.root, credentials=("", ""))

    def test_actual_worker_missing_credentials_is_structured_without_network(self):
        result = self.runner.call(tool.NAME, {"task_id": "existing-1"}, threading.Event())
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "config")

    def test_wall_clock_deadline_kills_a_stalled_worker(self):
        real_popen = subprocess.Popen
        processes = []
        def launch(_args, **kwargs):
            process = real_popen([sys.executable, "-c", "import sys,time; sys.stdin.read(); time.sleep(30)"], **kwargs)
            processes.append(process)
            return process
        self.runner.TIMEOUT = 0.2
        start = time.monotonic()
        with mock.patch.object(native_tools.subprocess, "Popen", side_effect=launch):
            result = self.runner.call(tool.NAME, {"task_id": "existing-1"}, threading.Event())
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["task_id"], "existing-1")
        self.assertLess(time.monotonic() - start, 3)
        self.assertIsNotNone(processes[0].poll())

    def test_cancelled_call_never_starts_a_worker(self):
        stop = threading.Event()
        stop.set()
        with mock.patch.object(native_tools.subprocess, "Popen") as launch:
            self.assertTrue(self.runner.call(tool.NAME, {"task_id": "existing-1"}, stop)["cancelled"])
            launch.assert_not_called()

    def test_unexpected_worker_failure_recovers_durable_id(self):
        real_popen = subprocess.Popen
        code = ("import sys,json,pathlib; p=json.load(sys.stdin); r=pathlib.Path(p['record_path']); "
                "r.parent.mkdir(parents=True,exist_ok=True); "
                "r.write_text(json.dumps({'task_id':'accepted-1','state':'processing','submission_started':True})); "
                "print(json.dumps({'success':False,'stage':'worker','error':'Synthetic failure'}))")
        def launch(_args, **kwargs):
            return real_popen([sys.executable, "-c", code], **kwargs)
        with mock.patch.object(native_tools.subprocess, "Popen", side_effect=launch):
            result = self.runner.call(tool.NAME, {"image_path": "synthetic.png"}, threading.Event())
        self.assertEqual(result["task_id"], "accepted-1")
        self.assertTrue(result["generation_may_be_billable"])
        self.assertNotIn("timed_out", result)

    def test_schema_has_original_inputs_and_no_credentials(self):
        spec = self.runner.specs[0]
        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], tool.NAME)
        self.assertEqual(set(spec["inputSchema"]["properties"]), {"image_path", "views", "quality", "task_id"})
        self.assertNotIn("credentials", json.dumps(spec))


class NativeStdioTests(unittest.TestCase):
    def test_native_readback_and_failure_are_visible_in_chat_projection(self):
        from session_state import SessionState
        session = SessionState()
        client = transport.CodexClient(session.apply)
        client._busy, client._thread_id, client._turn_id = True, "t", "u"
        try:
            result = {"success": False, "stage": "poll", "task_id": "existing-1"}
            client._notification("item/completed", {"threadId": "t", "turnId": "u",
                                 "item": {"id": "i", "type": "dynamicToolCall", "tool": tool.NAME,
                                          "status": "completed", "success": False,
                                          "contentItems": [{"type": "inputText", "text": json.dumps(result)}]}})
            row = session.tool_calls[0]
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["result"]["structuredContent"], result)
            self.assertEqual(json.loads(row["content"][0]["text"]), result)
        finally:
            session.resources.close()

    def test_real_stdio_registration_and_result_without_mcp(self):
        events = queue.Queue()
        release = threading.Event()
        class Registry:
            specs = [tool.SPEC]
            def call(self, name, args, cancel):
                release.wait(3)
                return {"success": True, "task_id": args["task_id"]}
        client = transport.CodexClient(events.put, native_tools=Registry())
        real_popen = subprocess.Popen
        def popen(_args, **options):
            return real_popen([sys.executable, str(ROOT / "tests/fixtures/fake_native_server.py")], **options)
        def wait_for(kind):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                event = events.get(timeout=max(0.01, deadline - time.monotonic()))
                if event["type"] == "error":
                    self.fail(event["text"])
                if event["type"] == kind:
                    return event
            self.fail("Missing event " + kind)
        with mock.patch.object(transport.subprocess, "Popen", side_effect=popen):
            try:
                client.start(cwd=str(ROOT), mcp_command="")
                wait_for("ready")
                client.send("Resume existing job", {})
                self.assertEqual(wait_for("delta")["text"], "Transport stays responsive")
                release.set()
                completed = wait_for("tool")
                self.assertEqual(completed["phase"], "completed")
                self.assertTrue(completed["item"]["success"])
                wait_for("done")
            finally:
                release.set()
                client.close()
                wait_for("closed")


class NativeDispatchTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = []
        class Registry:
            specs = [tool.SPEC]
        self.registry = Registry()
        def run(name, arguments, cancel):
            self.calls.append((name, arguments, cancel))
            self.entered.set()
            while not self.release.wait(0.01) and not cancel.is_set():
                pass
            return {"success": not cancel.is_set(), "task_id": "existing-1"}
        self.registry.call = run
        self.client = transport.CodexClient(self.events.append, native_tools=self.registry)
        self.client._thread_id = "thread-1"
        self.client._turn_id = "turn-1"
        self.client._busy = True
        self.params = {"threadId": "thread-1", "turnId": "turn-1", "callId": "call-1",
                       "tool": tool.NAME, "arguments": {"task_id": "existing-1"}}

    def tearDown(self):
        self.release.set()
        self.client._cancel_native_tools()

    def test_native_execution_does_not_block_transport_and_returns_json_content(self):
        before = time.monotonic()
        self.client._server_request("req-1", "item/tool/call", self.params)
        self.assertLess(time.monotonic() - before, 0.1)
        self.assertTrue(self.entered.wait(1))
        self.client._notification("item/agentMessage/delta", {
            "threadId": "thread-1", "turnId": "turn-1", "itemId": "msg-1", "delta": "Still responsive"})
        self.assertTrue(any(e["type"] == "delta" for e in self.events))
        self.release.set()
        kind, data = self.client._events.get(timeout=1)
        self.assertEqual(kind, "native_result")
        self.client._finish_native_tool(*data)
        response = json.loads(self.client._writes.get_nowait())
        self.assertTrue(response["result"]["success"])
        item = response["result"]["contentItems"][0]
        self.assertEqual(item["type"], "inputText")
        self.assertEqual(json.loads(item["text"])["task_id"], "existing-1")

    def test_foreign_or_replayed_call_never_launches_another_job(self):
        self.client._server_request("bad", "item/tool/call", {**self.params, "threadId": "other"})
        self.assertFalse(self.calls)
        self.client._server_request("req-1", "item/tool/call", self.params)
        self.assertTrue(self.entered.wait(1))
        self.client._server_request("req-2", "item/tool/call", self.params)
        self.assertEqual(len(self.calls), 1)

    def test_read_only_mode_never_runs_provider(self):
        self.client.permission_mode = "read_only"
        self.client._server_request("req-1", "item/tool/call", self.params)
        self.assertFalse(self.calls)
        response = json.loads(self.client._writes.get_nowait())
        self.assertFalse(response["result"]["success"])

    def test_on_request_approval_then_cancellation(self):
        self.client.permission_mode = "on_request"
        self.client._server_request("req-1", "item/tool/call", self.params)
        self.assertFalse(self.calls)
        self.assertEqual(self.events[-1]["type"], "approval")
        self.client._answer_approval("req-1", True)
        self.assertTrue(self.entered.wait(1))
        self.client._cancel_native_tools()
        _, data = self.client._events.get(timeout=1)
        self.client._finish_native_tool(*data)
        response = json.loads(self.client._writes.get_nowait())
        self.assertFalse(response["result"]["success"])

    def test_thread_registration_uses_dynamic_tools(self):
        self.client._busy = False
        with mock.patch.object(self.client, "_request") as request:
            self.client._models({"data": []}, str(ROOT))
        method, params, _ = request.call_args.args
        self.assertEqual(method, "thread/start")
        self.assertEqual(params["dynamicTools"], [tool.SPEC])


if __name__ == "__main__":
    unittest.main()
