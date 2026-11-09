"""Real loopback HTTP tests, without bpy, a browser, or external services."""
import contextlib
import base64
import http.client
import importlib.util
import io
import json
from pathlib import Path
import queue
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("web_bridge_under_test", ROOT / "blender_codex/web_bridge.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WebBridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.assets = Path(self.directory.name) / "web"
        self.assets.mkdir()
        (self.assets / "index.html").write_text("<!doctype html><title>Codex local UI</title>", encoding="utf-8")
        (self.assets / "app.js").write_text("'use strict';", encoding="utf-8")
        (self.assets / "styles.css").write_text("body { color: white; }", encoding="utf-8")
        patcher = mock.patch.object(module, "_ASSET_ROOT", self.assets)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.bridge = module.WebBridge()
        self.bridge.ACTION_TIMEOUT = 0.35
        self.url = self.bridge.start()
        self.origin = self.url.split("/#")[0]
        self.port = urlsplit(self.url).port
        self.addCleanup(self.bridge.stop)

    def request(self, method, path, body=None, headers=None, auth=True):
        request_headers = {"X-Codex-Token": self.bridge.token} if auth else {}
        if body is not None and not isinstance(body, (str, bytes)):
            body = json.dumps(body).encode()
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body, request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def action_request_async(self, command, headers=None):
        result = queue.Queue()

        def run():
            try:
                result.put(self.request("POST", "/api/action", command, headers))
            except Exception as error:
                result.put(error)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        return result, worker

    def action_response(self, result, worker):
        response = result.get(timeout=3)
        worker.join(timeout=1)
        if isinstance(response, Exception):
            raise response
        return response

    def test_start_loopback_url_token_and_idempotent_lifecycle(self):
        self.assertEqual(urlsplit(self.url).hostname, "127.0.0.1")
        self.assertEqual(len(self.bridge.token), 64)
        self.assertEqual(urlsplit(self.url).fragment, "token=" + self.bridge.token)
        self.assertEqual(self.bridge.start(), self.url)
        self.bridge.stop()
        self.bridge.stop()
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", self.port), timeout=0.3)
        old_token = self.bridge.token
        new_url = self.bridge.start()
        self.assertNotEqual(old_token, self.bridge.token)
        self.port = urlsplit(new_url).port
        self.assertEqual(self.request("GET", "/api/state", headers={"X-Codex-Token": old_token})[0], 401)

    def test_static_page_no_token_csp_and_no_cors(self):
        status, headers, body = self.request("GET", "/", auth=False)
        self.assertEqual(status, 200)
        self.assertIn(b"Codex local UI", body)
        self.assertNotIn(self.bridge.token.encode(), body)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        scripts = next(part for part in headers["Content-Security-Policy"].split(";") if "script-src" in part)
        self.assertNotIn("unsafe-inline", scripts)
        self.assertNotIn("unsafe-eval", scripts)
        self.assertIn("style-src 'self' 'unsafe-inline'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.request("GET", "/app.js", auth=False)[0], 200)
        self.assertEqual(self.request("GET", "/styles.css", auth=False)[0], 200)

    def test_real_component_bundle_size_has_separate_bounded_static_allowance(self):
        self.assertEqual(self.bridge.MAX_ASSET_BYTES, 16 * 1024 * 1024)
        body = b"//" + b"x" * (2 * 1024 * 1024 + 1)
        (self.assets / "app.js").write_bytes(body)
        request_limit = self.bridge.MAX_BODY_BYTES
        status, headers, received = self.request("GET", "/app.js", auth=False)
        self.assertEqual(status, 200)
        self.assertEqual(received, body)
        self.assertEqual(int(headers["Content-Length"]), len(body))
        self.bridge.MAX_ASSET_BYTES = 1024
        self.assertEqual(self.request("GET", "/app.js", auth=False)[0], 404)
        self.assertEqual(self.bridge.MAX_BODY_BYTES, request_limit)

    def test_api_authentication_required_and_token_not_in_query(self):
        self.assertEqual(self.request("GET", "/api/state", auth=False)[0], 401)
        self.assertEqual(self.request("GET", "/api/state", headers={"X-Codex-Token": "bad"})[0], 401)
        self.assertEqual(self.request("GET", "/api/state?token=" + self.bridge.token, auth=False)[0], 404)
        self.assertEqual(self.request("POST", "/api/action", {"action": "stop"}, auth=False)[0], 401)
        self.assertTrue(self.bridge.commands.empty())

    def test_host_and_origin_checks_even_with_valid_token(self):
        for headers in ({"Host": "evil.example"}, {"Host": "localhost:%d" % self.port},
                        {"Origin": "https://evil.example"}, {"Origin": "null"},
                        {"Origin": "http://127.0.0.1:1"}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("GET", "/api/state", headers=headers)[0], 403)
                self.assertEqual(self.request("POST", "/api/action", {"action": "stop"}, headers)[0], 403)
        self.assertTrue(self.bridge.commands.empty())
        self.assertEqual(self.request("GET", "/api/state", headers={"Origin": self.origin})[0], 200)

    def test_snapshot_is_copied_and_connection_settings_allowlisted(self):
        state = {"ready": True, "busy": False, "status": "Ready", "error": "", "activity": "",
                 "messages": [{"role": "user", "text": "Hallo 🧊", "has_view": True}], "approvals": [],
                 "context": {"filepath": "a.blend", "is_unsaved": False, "active_object": "Cube", "selected_objects": ["Cube"]},
                 "settings": {"codex_path": "codex", "mcp_command": "uvx", "mcp_args": [], "client_secret": "NEVER-SEND"},
                 "token": "NEVER-SEND"}
        self.bridge.publish(state)
        state["messages"][0]["text"] = "mutated"
        status, _, body = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        decoded = json.loads(body)
        self.assertEqual(decoded["messages"][0]["text"], "Hallo 🧊")
        self.assertNotIn(b"NEVER-SEND", body)
        self.assertFalse(decoded["busy"])

    def test_resource_bytes_require_token_and_never_accept_local_paths(self):
        png = b"\x89PNG\r\n\x1a\nimage"
        resource = self.bridge.resources.add("view.png", "image/png", png)
        for url in (resource["url"], resource["resource_url"]):
            self.assertEqual(self.request("GET", url, auth=False)[0], 401)
            status, headers, body = self.request("GET", url)
            self.assertEqual(status, 200)
            self.assertEqual(body, png)
            self.assertEqual(headers["Content-Type"], "image/png")
            self.assertIn("attachment; filename*=", headers["Content-Disposition"])
        self.assertEqual(self.request("GET", "/api/resources/C:/private.txt")[0], 404)
        self.assertEqual(self.request("GET", "/api/resource/" + "f" * 48)[0], 404)
        self.assertEqual(self.request("GET", resource["url"], headers={"Origin": "https://evil.example"})[0], 403)

    def test_over_four_mib_snapshot_keeps_server_alive_and_details_authenticated(self):
        output = "actual tool output " * 150000
        self.bridge.publish({"ready": True, "busy": False, "messages": [], "tool_calls": [
            {"id": "tool", "seq": 1, "status": "completed", "result": output, "content": [{"type": "text", "text": output}]}]})
        status, _, body = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertLessEqual(len(body), 4 * 1024 * 1024)
        self.assertEqual(self.bridge.MAX_STATE_BYTES, 4 * 1024 * 1024)
        state = json.loads(body)
        self.assertTrue(state["ready"])
        handle = state["tool_calls"][0]["projection"]["detail_resource_id"]
        self.assertEqual(self.request("GET", "/api/resources/" + handle, auth=False)[0], 401)
        resource = self.request("GET", "/api/resources/" + handle)
        self.assertEqual(resource[0], 200)
        self.assertEqual(json.loads(resource[2])["result"], output)
        self.assertEqual(self.request("GET", "/api/state")[0], 200)

    def test_new_state_fields_survive_publish_without_losing_correlations(self):
        fields = {"models": [{"id": "real-id"}], "selected_model": "real-id", "reasoning_effort": "high",
                  "permission_mode": "full_access", "permission_modes": [{"id": "full_access"}],
                  "thread_id": "thread-real", "tool_calls": [{"id": '["thread-real","turn-real","item-real"]', "result": {"unknown": True}}],
                  "attachments": [], "artifacts": [], "capabilities": {"can_upload_attachments": True}}
        self.bridge.publish(fields)
        snapshot = json.loads(self.request("GET", "/api/state")[2])
        for key, value in fields.items():
            self.assertEqual(snapshot[key], value)

    def test_deepblick_selection_upload_and_form_actions_reach_mainthread_unchanged(self):
        commands = [
            {"action": "markup_cancel"},
            {"action": "threads/list"}, {"action": "threads/new"},
            {"action": "threads/open", "thread_id": "plugin-thread"},
            {"action": "threads/rename", "thread_id": "plugin-thread", "title": "Renamed chat"},
            {"action": "select_model", "model_id": "actual-id", "reasoning_effort": "high"},
            {"action": "select_effort", "reasoning_effort": "medium"},
            {"action": "set_permission_mode", "permission_mode": "read_only"},
            {"action": "upload_attachment", "name": "note.txt", "mime_type": "text/plain", "data_base64": base64.b64encode(b"hi").decode()},
            {"action": "remove_attachment", "resource_id": "a" * 48},
            {"action": "respond", "request_id": 7, "approved": True, "values": {"count": 2}},
            {"action": "respond", "request_id": "q", "approved": True, "answers": {"color": ["Blue"]}},
            {"action": "send", "text": "Use attached file", "attachment_ids": ["a" * 48]},
        ]
        for command in commands:
            with self.subTest(action=command["action"]):
                result, worker = self.action_request_async(command)
                queued, reply = self.bridge.commands.get(timeout=2)
                self.assertEqual(queued, command)
                reply.put({"ok": True})
                self.assertEqual(self.action_response(result, worker)[0], 200)

    def test_action_queue_handoff_preserves_fields_and_mainthread_reply(self):
        command = {"action": "send", "text": "Change selected cube", "include_view": True}
        result, worker = self.action_request_async(command, {"Origin": self.origin})
        queued, reply = self.bridge.commands.get(timeout=2)
        self.assertEqual(queued, command)
        self.assertTrue(result.empty())
        reply.put({"ok": True})
        status, _, body = self.action_response(result, worker)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})

    def test_all_action_variants_validate_and_preserve_commands(self):
        commands = [{"action": name} for name in ("connect", "disconnect", "new_chat", "stop", "draw", "hide_panel")]
        commands.extend([{"action": "approve", "request_id": 7, "approved": False},
                         {"action": "approve", "request_id": "server-request", "approved": True},
                         {"action": "settings", "codex_path": "codex", "mcp_command": "", "mcp_args": ""},
                         {"action": "settings", "codex_path": "codex", "mcp_command": "uvx", "mcp_args": '["mcp-for-blender"]'}])
        for command in commands:
            with self.subTest(action=command):
                result, worker = self.action_request_async(command)
                queued, reply = self.bridge.commands.get(timeout=2)
                self.assertEqual(queued, command)
                reply.put({"ok": True})
                self.assertEqual(self.action_response(result, worker)[0], 200)

    def test_mainthread_error_and_invalid_reply_are_bounded(self):
        for reply_value, expected in (({"ok": False, "error": "No 3D editor found"}, 400),
                                      ({"unexpected": True}, 500)):
            result, worker = self.action_request_async({"action": "draw"})
            _, reply = self.bridge.commands.get(timeout=2)
            reply.put(reply_value)
            self.assertEqual(self.action_response(result, worker)[0], expected)

    def test_timeout_discards_unclaimed_command(self):
        start = time.monotonic()
        status, _, body = self.request("POST", "/api/action", {"action": "send", "text": "Do not execute later"})
        self.assertEqual(status, 504)
        self.assertLess(time.monotonic() - start, 2)
        self.assertIn(b"check state before retrying", body)
        self.assertTrue(self.bridge.commands.empty())

    def test_queue_capacity_rejects_action_without_displacing_pending_work(self):
        for index in range(self.bridge.commands.maxsize):
            self.bridge.commands.put_nowait(({"action": "stop", "test_index": index}, queue.Queue()))
        self.assertEqual(self.request("POST", "/api/action", {"action": "draw"})[0], 503)
        self.assertEqual(self.bridge.commands.qsize(), self.bridge.commands.maxsize)

    def test_duplicate_or_excessive_content_length_is_rejected(self):
        for values in (("2", "2"), ("9" * 100,)):
            with self.subTest(values=values):
                connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
                try:
                    connection.putrequest("POST", "/api/action")
                    connection.putheader("X-Codex-Token", self.bridge.token)
                    connection.putheader("Content-Type", "application/json")
                    for value in values:
                        connection.putheader("Content-Length", value)
                    connection.endheaders(b"{}")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 411)
                    response.read()
                finally:
                    connection.close()
        self.assertTrue(self.bridge.commands.empty())

    def test_claimed_command_can_reply_after_timeout_without_blocking(self):
        result, worker = self.action_request_async({"action": "stop"})
        _, reply = self.bridge.commands.get(timeout=2)
        self.assertEqual(self.action_response(result, worker)[0], 504)
        reply.put_nowait({"ok": True})
        self.assertTrue(self.bridge.commands.empty())

    def test_stop_cancels_pending_http_without_replay_on_restart(self):
        result, worker = self.action_request_async({"action": "send", "text": "pending"})
        deadline = time.monotonic() + 2
        while self.bridge.commands.empty() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(self.bridge.commands.empty())
        self.bridge.stop()
        self.assertEqual(self.action_response(result, worker)[0], 503)
        self.assertTrue(self.bridge.commands.empty())
        self.bridge.start()
        self.assertTrue(self.bridge.commands.empty())

    def test_invalid_actions_never_enter_blender_queue(self):
        commands = [[], {}, {"action": "exec", "code": "bad"}, {"action": "stop", "extra": True},
                    {"action": "send", "text": ""}, {"action": "send", "text": "x", "include_view": "true"},
                    {"action": "approve", "request_id": True, "approved": True},
                    {"action": "approve", "request_id": "a", "approved": 1},
                    {"action": "settings"}, {"action": "settings", "mcp_args": {}},
                    {"action": "settings", "codex_path": "bad\npath"}]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.request("POST", "/api/action", command)[0], 400)
        self.assertTrue(self.bridge.commands.empty())

    def test_body_bounds_json_content_type_and_transfer_encoding(self):
        self.assertEqual(self.request("POST", "/api/action", b"{}",
                                      {"Content-Type": "application/json", "Content-Length": str(self.bridge.MAX_BODY_BYTES + 1)})[0], 413)
        self.assertEqual(self.request("POST", "/api/action", b"{}", {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/action", b"not-json", {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/action", b"{}", {"Transfer-Encoding": "chunked"})[0], 400)
        self.assertTrue(self.bridge.commands.empty())

    def test_traversal_absolute_urls_queries_and_unknown_assets_rejected(self):
        (self.assets.parent / "secret.txt").write_text("DO-NOT-SERVE")
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/%2f..%2fsecret.txt", "/app.js?token=secret",
                     "//evil.example/app.js", "http://evil.example/app.js", "/unknown.js", "/api/action"):
            with self.subTest(path=path):
                status, _, body = self.request("GET", path, auth=False)
                self.assertIn(status, (403, 404))
                self.assertNotIn(b"DO-NOT-SERVE", body)

    def test_preflight_refused_and_no_request_logging(self):
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            status, headers, body = self.request("OPTIONS", "/api/action",
                                                headers={"Origin": "https://evil.example"})
            self.assertEqual(status, 403)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            self.request("POST", "/api/action", b"private-prompt-DO-NOT-LOG", {"Content-Type": "application/json"})
        self.assertEqual(captured.getvalue(), "")
        self.assertNotIn(self.bridge.token.encode(), body)

    def test_duplicate_host_and_token_headers_rejected(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            connection.putrequest("GET", "/api/state")
            connection.putheader("Host", "evil.example")
            connection.putheader("X-Codex-Token", self.bridge.token)
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
        finally:
            connection.close()
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            connection.putrequest("GET", "/api/state")
            connection.putheader("X-Codex-Token", self.bridge.token)
            connection.putheader("X-Codex-Token", self.bridge.token)
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 401)
            response.read()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
