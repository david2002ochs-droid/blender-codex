"""Fake HTTPS peer exercises real urllib encoding, status and redirect handling."""
import base64
from email import policy
from email.message import Message
from email.parser import BytesParser
import http.client
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import urllib.error
import urllib.request
import urllib.response

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hi3d_under_test", ROOT / "blender_codex/hi3d.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Hi3DClient, Hi3DError = module.Hi3DClient, module.Hi3DError
BASE = "https://api.hitem3d.ai/open-api/v1"
SECRET = "test-secret-DO-NOT-ECHO"
TOKEN = "fake-token-DO-NOT-ECHO"
URL = "https://cdn.example.com/model.glb?signature=DO-NOT-ECHO"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-data"


def glb():
    data = b'{"asset":{"version":"2.0"}} '
    data += b" " * (-len(data) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(data)) + struct.pack("<I4s", len(data), b"JSON") + data


class FakeHTTPS(urllib.request.BaseHandler):
    # This handler precedes real HTTPSHandler; no socket can be opened.
    handler_order = 100

    def __init__(self):
        self.steps = []
        self.requests = []

    def add(self, method, url, data=None, status=200, headers=None, error=None, raw=None):
        body = raw if raw is not None else json.dumps({"code": 200, "data": data or {}}).encode()
        self.steps.append((method, url, body, status, headers or {}, error))

    def https_open(self, request):
        if not self.steps:
            raise AssertionError("Unexpected fake HTTPS request")
        method, url, body, status, headers, error = self.steps.pop(0)
        if request.get_method() != method or request.full_url != url:
            raise AssertionError("Unexpected fake HTTPS method or URL")
        self.requests.append(request)
        if error is not None:
            raise error
        message = Message()
        for key, value in headers.items():
            message[key] = str(value)
        response = urllib.response.addinfourl(io.BytesIO(body), message, url, status)
        response.msg = "Fake response"
        return response


class Hi3DTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.image = self.root / "secret-local-filename.png"
        self.image.write_bytes(PNG)
        self.client = Hi3DClient("test-client", SECRET)
        self.peer = FakeHTTPS()
        self.client._api = urllib.request.build_opener(module._NoRedirect(), self.peer)
        self.client._downloads = urllib.request.build_opener(module._DownloadRedirect(), self.peer)

    def tearDown(self):
        self.assertFalse(self.peer.steps, "Unconsumed fake HTTP expectations")

    def auth(self, token=TOKEN):
        self.peer.add("POST", BASE + "/auth/token", {"accessToken": token})

    def assert_safe(self, error):
        text = str(error)
        for sensitive in (SECRET, TOKEN, URL, "DO-NOT-ECHO", "secret-local-filename"):
            self.assertNotIn(sensitive, text)

    def multipart(self, request):
        parsed = BytesParser(policy=policy.default).parsebytes(
            ("Content-Type: " + request.get_header("Content-type") + "\r\n\r\n").encode() + request.data)
        return {part.get_param("name", header="content-disposition"): part for part in parsed.iter_parts()}

    def test_auth_and_balance_use_fixed_api_and_cache_token(self):
        self.auth()
        self.peer.add("GET", BASE + "/balance", {"totalBalance": "50.5"})
        self.peer.add("GET", BASE + "/balance", {"totalBalance": 49})
        self.assertEqual(self.client.balance(), 50.5)
        self.assertEqual(self.client.balance(), 49)
        auth, first, second = self.peer.requests
        self.assertEqual(auth.get_header("Authorization"), "Basic " +
                         base64.b64encode(("test-client:" + SECRET).encode()).decode())
        self.assertEqual(auth.data, b"{}")
        self.assertEqual(first.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertEqual(second.get_header("Authorization"), "Bearer " + TOKEN)

    def test_submit_multipart_defaults_and_local_filename_privacy(self):
        self.auth()
        self.peer.add("POST", BASE + "/submit-task", {"task_id": "task.example-1"})
        self.assertEqual(self.client.submit(self.image), "task.example-1")
        parts = self.multipart(self.peer.requests[-1])
        for key, value in {"model": "hi3dv3.0", "request_type": "3", "resolution": "2048quality",
                           "pbr": "1", "format": "2", "face": "2000000"}.items():
            self.assertEqual(parts[key].get_content(), value)
        self.assertEqual(parts["images"].get_payload(decode=True), PNG)
        self.assertEqual(parts["images"].get_filename(), "input.png")

    def test_master_conservative_faces_and_no_pbr(self):
        self.auth()
        self.peer.add("POST", BASE + "/submit-task", {"task_id": "master-1"})
        self.client.submit(self.image, "2048master", False)
        parts = self.multipart(self.peer.requests[-1])
        self.assertEqual(parts["resolution"].get_content(), "2048master")
        self.assertEqual(parts["face"].get_content(), "2000000")
        self.assertEqual(parts["pbr"].get_content(), "0")

    def test_estimates_and_invalid_resolution(self):
        self.assertEqual(module.estimate_credits(), 45)
        self.assertEqual(self.client.estimate_credits("2048quality", False), 40)
        self.assertEqual(module.estimate_credits("2048master"), 145)
        self.assertEqual(module.estimate_credits("2048master", False), 140)
        with self.assertRaises(Hi3DError):
            self.client.submit(self.image, "other")
        self.assertFalse(self.peer.requests)

    def test_query_whitelists_fields_and_preserves_task_id(self):
        self.auth()
        for state in ("created", "queueing", "processing", "success", "failed"):
            self.peer.add("GET", BASE + "/query-task?task_id=task-1",
                          {"state": state, "task_id": "task-1", "url": URL,
                           "cover_url": "https://cdn.example.com/cover.webp", "message": SECRET})
            result = self.client.query("task-1")
            self.assertEqual(result["state"], state)
            self.assertEqual(result["task_id"], "task-1")
            self.assertEqual(result["url"], URL)
            self.assertNotIn("message", result)

    def test_read_only_auth_retry_is_bounded(self):
        self.auth()
        self.peer.add("GET", BASE + "/balance", status=401)
        self.auth("new-token")
        self.peer.add("GET", BASE + "/balance", {"totalBalance": 10})
        self.assertEqual(self.client.balance(), 10)
        self.assertEqual(len(self.peer.requests), 4)
        self.assertEqual(self.peer.requests[-1].get_header("Authorization"), "Bearer new-token")

    def test_repeated_401_stops_after_one_read_retry(self):
        self.auth()
        self.peer.add("GET", BASE + "/balance", status=401)
        self.auth()
        self.peer.add("GET", BASE + "/balance", status=401)
        with self.assertRaises(Hi3DError) as caught:
            self.client.balance()
        self.assert_safe(caught.exception)
        self.assertEqual(len(self.peer.requests), 4)

    def test_submit_timeout_does_not_retry_and_warns_about_existing_task(self):
        self.auth()
        self.peer.add("POST", BASE + "/submit-task", error=TimeoutError(SECRET + URL))
        with self.assertRaises(Hi3DError) as caught:
            self.client.submit(self.image)
        self.assert_safe(caught.exception)
        self.assertIn("may already exist", str(caught.exception))
        self.assertEqual(len(self.peer.requests), 2)

    def test_submit_401_does_not_retry(self):
        self.auth()
        self.peer.add("POST", BASE + "/submit-task", status=401)
        with self.assertRaises(Hi3DError) as caught:
            self.client.submit(self.image)
        self.assert_safe(caught.exception)
        self.assertEqual(len(self.peer.requests), 2)

    def test_api_redirect_refused_before_forwarding_credentials(self):
        self.peer.add("POST", BASE + "/auth/token", status=307, headers={"Location": URL})
        with self.assertRaises(Hi3DError) as caught:
            self.client.balance()
        self.assertIn("redirect", str(caught.exception))
        self.assert_safe(caught.exception)
        self.assertEqual(len(self.peer.requests), 1)

    def test_provider_echo_and_untrusted_error_code_are_never_displayed(self):
        self.peer.add("POST", BASE + "/auth/token", raw=json.dumps(
            {"code": SECRET, "message": SECRET + URL, "data": {"accessToken": TOKEN}}).encode())
        with self.assertRaises(Hi3DError) as caught:
            self.client.balance()
        self.assert_safe(caught.exception)

    def test_missing_credentials_and_unreadable_image_are_safe(self):
        with self.assertRaises(Hi3DError):
            Hi3DClient("", SECRET)
        with self.assertRaises(Hi3DError) as caught:
            self.client.submit(self.root / "secret-local-filename-missing.png")
        self.assert_safe(caught.exception)

    def test_oversized_empty_or_mismatched_image_rejected_before_http(self):
        for content in (b"", b"fake jpeg", PNG + b"x" * 20):
            with self.subTest(content=content[:8]):
                self.image.write_bytes(content)
                self.client.MAX_IMAGE_BYTES = len(PNG)
                with self.assertRaises(Hi3DError):
                    self.client.submit(self.image)
        self.assertFalse(self.peer.requests)

    def test_jpeg_and_webp_uploads(self):
        self.auth()
        for name, content, mime in (("a.jpeg", b"\xff\xd8\xffjpeg", "image/jpeg"),
                                    ("a.webp", b"RIFF\x00\x00\x00\x00WEBPdata", "image/webp")):
            image = self.root / name
            image.write_bytes(content)
            self.peer.add("POST", BASE + "/submit-task", {"task_id": "task-1"})
            self.client.submit(image)
            self.assertEqual(self.multipart(self.peer.requests[-1])["images"].get_content_type(), mime)

    def test_malformed_or_oversized_json_is_safe(self):
        self.peer.add("POST", BASE + "/auth/token", raw=(SECRET + URL).encode())
        with self.assertRaises(Hi3DError) as caught:
            self.client.balance()
        self.assert_safe(caught.exception)
        self.client.MAX_JSON_BYTES = 10
        self.auth()
        with self.assertRaises(Hi3DError):
            self.client.balance()

    def test_invalid_balance_rejected(self):
        self.auth()
        for value in (True, "nan", -1, {}, None):
            self.peer.add("GET", BASE + "/balance", {"totalBalance": value})
            with self.assertRaises(Hi3DError):
                self.client.balance()

    def test_bad_task_input_and_unknown_state(self):
        for task in ("", "../bad", SECRET + URL):
            with self.assertRaises(Hi3DError) as caught:
                self.client.query(task)
            self.assert_safe(caught.exception)
        self.auth()
        for value in ("unexpected", []):
            self.peer.add("GET", BASE + "/query-task?task_id=task-1", {"state": value})
            with self.assertRaises(Hi3DError):
                self.client.query("task-1")

    def test_download_atomic_valid_glb_without_authorization(self):
        self.client._token = TOKEN
        content = glb()
        self.peer.add("GET", URL, raw=content, headers={"Content-Length": len(content)})
        destination = self.root / "model.glb"
        destination.write_bytes(b"old file")
        self.assertEqual(self.client.download(URL, destination), str(destination))
        self.assertEqual(destination.read_bytes(), content)
        self.assertIsNone(self.peer.requests[-1].get_header("Authorization"))
        self.assertFalse(list(self.root.glob("*.part")))

    def test_https_redirect_has_no_auth_or_cookies(self):
        target = "https://other.example.com/result.glb?signature=second"
        self.peer.add("GET", URL, status=302, headers={"Location": target, "Set-Cookie": "secret-cookie"})
        self.peer.add("GET", target, raw=glb())
        self.client.download(URL, self.root / "result.glb")
        for request in self.peer.requests:
            self.assertIsNone(request.get_header("Authorization"))
            self.assertIsNone(request.get_header("Cookie"))

    def test_unsafe_download_schemes_hosts_and_credentials_rejected(self):
        for url in ("http://cdn.example.com/a", "file:///tmp/a", "https://u:p@cdn.example.com/a",
                    "https://localhost/a", "https://127.0.0.1/a", "https://10.0.0.2/a",
                    "https://[::1]/a", "https://cdn.example.com:8443/a", URL + "\nX: bad"):
            with self.subTest(url=url):
                with self.assertRaises(Hi3DError) as caught:
                    self.client.download(url, self.root / "result.glb")
                self.assert_safe(caught.exception)
        self.assertFalse(self.peer.requests)

    def test_https_to_http_redirect_refused(self):
        self.peer.add("GET", URL, status=302, headers={"Location": "http://cdn.example.com/result.glb"})
        with self.assertRaises(Hi3DError) as caught:
            self.client.download(URL, self.root / "result.glb")
        self.assert_safe(caught.exception)
        self.assertEqual(len(self.peer.requests), 1)

    def test_invalid_or_truncated_glb_preserves_destination_and_cleans_partial(self):
        destination = self.root / "result.glb"
        destination.write_bytes(b"original")
        for content in (b"not glb", glb()[:-1], b"glTF" + struct.pack("<II", 1, len(glb())) + glb()[12:]):
            self.peer.add("GET", URL, raw=content)
            with self.assertRaises(Hi3DError) as caught:
                self.client.download(URL, destination)
            self.assert_safe(caught.exception)
            self.assertEqual(destination.read_bytes(), b"original")
            self.assertFalse(list(self.root.glob("*.part")))

    def test_download_size_limit_with_and_without_header(self):
        self.client.MAX_GLB_BYTES = 24
        self.peer.add("GET", URL, raw=glb(), headers={"Content-Length": len(glb())})
        self.peer.add("GET", URL, raw=glb())
        for _ in range(2):
            with self.assertRaises(Hi3DError):
                self.client.download(URL, self.root / "result.glb")
        self.assertFalse(list(self.root.glob("*.part")))

    def test_download_length_header_mismatch_and_network_failure_are_safe(self):
        self.peer.add("GET", URL, raw=glb(), headers={"Content-Length": len(glb()) + 1})
        with self.assertRaises(Hi3DError):
            self.client.download(URL, self.root / "result.glb")
        self.peer.add("GET", URL, error=urllib.error.URLError(URL + SECRET))
        with self.assertRaises(Hi3DError) as caught:
            self.client.download(URL, self.root / "result.glb")
        self.assert_safe(caught.exception)
        self.peer.add("GET", URL, error=http.client.IncompleteRead(b"secret"))
        with self.assertRaises(Hi3DError):
            self.client.download(URL, self.root / "result.glb")


if __name__ == "__main__":
    unittest.main()
