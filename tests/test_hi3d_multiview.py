"""Real multipart bytes and durable duplicate prevention; no provider traffic."""
import base64
from concurrent.futures import ThreadPoolExecutor
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.request
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "blender_codex"))
import hi3d
import hi3d_tool as tool
import native_tools
from test_hi3d import FakeHTTPS, BASE, SECRET, TOKEN, URL, glb


def png(red):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes([0, red, 0, 0]))) + chunk(b"IEND", b""))


# Actual 1x1 JPEG from Windows System.Drawing; WEBP is a 1x1 lossless image.
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
    "2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/"
    "8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkK"
    "FhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXG"
    "x8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAx"
    "EEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYa"
    "HiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK+ZP3E//Z")
WEBP = base64.b64decode("UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA==")


class MultiviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.views = []
        for i, role in enumerate(hi3d.VIEW_ORDER):
            path = self.root / (role + ".png")
            path.write_bytes(png(i * 60))
            self.views.append({"view": role, "image_path": str(path)})
        self.client = tool.ToolClient("test-client", SECRET)
        self.peer = FakeHTTPS()
        self.client._api = urllib.request.build_opener(self.peer)
        self.client._downloads = urllib.request.build_opener(self.peer)
        self.payload = {"arguments": {"views": self.views[:3]}, "credentials": ["test-client", SECRET],
                        "cwd": str(self.root), "record_path": str(self.root / "jobs/job.json"),
                        "output_dir": str(self.root / "models")}

    def auth(self):
        self.peer.add("POST", BASE + "/auth/token", {"accessToken": TOKEN})

    def success(self, submit=True, auth=True):
        if auth:
            self.auth()
        if submit:
            self.peer.add("POST", BASE + "/submit-task", {"task_id": "task-1"})
        self.peer.add("GET", BASE + "/query-task?task_id=task-1", {"state": "success", "url": URL})
        self.peer.add("GET", URL, raw=glb())

    def execute(self):
        return tool.execute(self.payload, lambda *_: self.client, sleep=lambda _: None)

    def test_multipart_two_three_four_views_order_mask_and_exact_bytes(self):
        self.auth()
        for views, mask in (([self.views[2], self.views[0]], "1010"),
                            (list(reversed(self.views[:3])), "1110"),
                            (list(reversed(self.views)), "1111")):
            with self.subTest(mask=mask):
                self.peer.add("POST", BASE + "/submit-task", {"task_id": "task-1"})
                self.client.submit(views=views)
                request = self.peer.requests[-1]
                message = BytesParser(policy=policy.default).parsebytes(
                    ("Content-Type: " + request.get_header("Content-type") + "\r\n\r\n").encode() + request.data)
                parts = list(message.iter_parts())
                fields = {p.get_param("name", header="content-disposition"): p for p in parts}
                self.assertNotIn("images", fields)
                self.assertEqual(fields["multi_images_bit"].get_content(), mask)
                files = [p for p in parts if p.get_param("name", header="content-disposition") == "multi_images"]
                expected = [v for v in self.views if v in views]
                self.assertEqual([p.get_filename() for p in files], [v["view"] + ".png" for v in expected])
                self.assertEqual([p.get_payload(decode=True) for p in files],
                                 [Path(v["image_path"]).read_bytes() for v in expected])
                self.assertNotIn(str(self.root).encode(), request.data)
        self.assertFalse(self.peer.steps)

    def test_invalid_view_contract_rejected_before_authentication(self):
        invalid = [[], self.views[:1], self.views + self.views[:1], self.views[1:3],
                   [self.views[0], self.views[0]],
                   [self.views[0], {"view": "top", "image_path": self.views[1]["image_path"]}],
                   [self.views[0], {"view": "left", "image_path": "relative.png"}],
                   [self.views[0], {**self.views[1], "extra": True}], None, "front"]
        for views in invalid:
            with self.subTest(views=views):
                self.payload["arguments"] = {"views": views}
                result = self.execute()
                self.assertFalse(result["success"])
                self.assertEqual(result["stage"], "input")
        self.payload["arguments"] = {"views": self.views[:2], "image_path": self.views[0]["image_path"]}
        self.assertEqual(self.execute()["stage"], "input")
        with self.assertRaises(hi3d.Hi3DError):
            self.client.submit(self.views[0]["image_path"], views=self.views[:2])
        self.assertFalse(self.peer.requests)
        self.assertFalse(Path(self.payload["record_path"]).exists())

    def test_missing_fake_truncated_and_oversized_view_prevent_any_upload(self):
        path = Path(self.views[1]["image_path"])
        for data in (b"", b"not png", b"\x89PNG\r\n\x1a\nfake", png(60)[:-1], png(60) + b"x"):
            path.write_bytes(data)
            self.assertEqual(self.execute()["stage"], "input")
        path.unlink()
        self.assertEqual(self.execute()["stage"], "input")
        path.write_bytes(png(60))
        self.client.MAX_IMAGE_BYTES = len(png(60)) - 1
        self.assertEqual(self.execute()["stage"], "input")
        self.assertFalse(self.peer.requests)

    def test_real_jpeg_webp_and_png_containers_and_truncation(self):
        for extension, data, mime in (("png", png(0), "image/png"), ("jpg", JPEG, "image/jpeg"),
                                       ("webp", WEBP, "image/webp")):
            with self.subTest(extension=extension):
                path = self.root / ("other." + extension)
                path.write_bytes(data)
                views = [self.views[0], {"view": "right", "image_path": str(path)}]
                images = self.client.prepare_images(views=views)
                self.assertEqual(images[1][1][2], mime)
                path.write_bytes(data[:-3])
                with self.assertRaises(hi3d.Hi3DError):
                    self.client.prepare_images(views=views)
        self.assertFalse(self.peer.requests)

    def test_fingerprint_roles_quality_bytes_canonical_order_not_paths(self):
        images = self.client.prepare_images(views=self.views[:3])
        identity = tool.request_identity(images, "standard")
        reversed_images = self.client.prepare_images(views=list(reversed(self.views[:3])))
        self.assertEqual(identity, tool.request_identity(reversed_images, "standard"))
        for item, source in zip(identity["request"]["images"], self.views):
            self.assertEqual(item["view"], source["view"])
            self.assertEqual(item["sha256"], hashlib.sha256(Path(source["image_path"]).read_bytes()).hexdigest())
        self.assertNotEqual(identity["fingerprint"], tool.request_identity(images, "master")["fingerprint"])
        swapped = [self.views[0], {"view": "back", "image_path": self.views[2]["image_path"]},
                   {"view": "left", "image_path": self.views[1]["image_path"]}]
        self.assertNotEqual(identity, tool.request_identity(self.client.prepare_images(views=swapped), "standard"))
        Path(self.views[1]["image_path"]).write_bytes(png(42))
        self.assertNotEqual(identity, tool.request_identity(self.client.prepare_images(views=self.views[:3]), "standard"))

    def test_duplicate_reordered_request_blocks_without_network_and_recovers_task_id(self):
        self.success()
        self.assertTrue(self.execute()["success"])
        before = len(self.peer.requests)
        self.payload["arguments"]["views"].reverse()
        self.payload["record_path"] = str(self.root / "jobs/second.json")
        result = self.execute()
        self.assertEqual(result["stage"], "journal")
        self.assertEqual(result["task_id"], "task-1")
        self.assertIn("Resume", result["note"])
        self.assertEqual(len(self.peer.requests), before)
        self.assertNotIn(SECRET, json.dumps(result))

    def test_ambiguous_submit_remains_blocked_across_worker_restarts(self):
        self.auth()
        self.peer.add("POST", BASE + "/submit-task", error=TimeoutError("fake"))
        self.assertTrue(self.execute()["generation_may_be_billable"])
        self.payload["record_path"] = str(self.root / "jobs/retry.json")
        result = self.execute()
        self.assertEqual(result["stage"], "journal")
        self.assertNotIn("task_id", result)
        self.assertEqual(len(self.peer.requests), 2)

    def test_conflicting_job_record_is_not_overwritten(self):
        self.success()
        self.assertTrue(self.execute()["success"])
        path = Path(self.payload["record_path"])
        original = path.read_bytes()
        self.payload["arguments"]["quality"] = "master"
        self.assertEqual(self.execute()["stage"], "journal")
        self.assertEqual(path.read_bytes(), original)

    def test_resume_ignores_conflicting_missing_image_inputs_and_never_submits(self):
        self.payload["arguments"] = {"task_id": "task-1", "image_path": "missing.png",
                                     "views": [{"view": "wrong", "image_path": "missing2.png"}]}
        self.success(submit=False)
        with mock.patch.object(self.client, "prepare_images", side_effect=AssertionError("must not read images")):
            self.assertTrue(self.execute()["success"])
        self.assertFalse(any(r.full_url.endswith("submit-task") for r in self.peer.requests))

    def test_upload_uses_snapshots_matching_journal_even_if_sources_change(self):
        self.success()
        original = Path(self.views[0]["image_path"]).read_bytes()
        claim = tool.claim_submission
        def mutate_after_validation(path, record):
            result = claim(path, record)
            Path(self.views[0]["image_path"]).write_bytes(png(255))
            return result
        with mock.patch.object(tool, "claim_submission", side_effect=mutate_after_validation):
            self.assertTrue(self.execute()["success"])
        self.assertIn(original, self.peer.requests[1].data)
        record = json.loads(Path(self.payload["record_path"]).read_text())
        self.assertEqual(record["request"]["images"][0]["sha256"], hashlib.sha256(original).hexdigest())

    def test_created_queueing_processing_are_polled_and_journaled(self):
        self.auth()
        self.peer.add("POST", BASE + "/submit-task", {"task_id": "task-1"})
        for state in ("created", "queueing", "processing"):
            self.peer.add("GET", BASE + "/query-task?task_id=task-1", {"state": state})
        self.success(submit=False, auth=False)
        observed = []
        def observe(delay):
            self.assertEqual(delay, 5)
            observed.append(json.loads(Path(self.payload["record_path"]).read_text())["state"])
        result = tool.execute(self.payload, lambda *_: self.client, sleep=observe)
        self.assertTrue(result["success"])
        self.assertEqual(observed, ["created", "queueing", "processing"])

    def test_registry_has_one_public_name_and_accepts_legacy_dispatch(self):
        registry = native_tools.NativeTools(self.root, credentials=("", ""))
        self.assertEqual([s["name"] for s in registry.specs], ["image_to_3d"])
        stop = threading.Event()
        stop.set()
        self.assertTrue(registry.call("hi3d_image_to_3d", {"task_id": "task-1"}, stop)["cancelled"])

    def test_concurrent_duplicate_workers_obtain_exactly_one_submission_claim(self):
        identity = tool.request_identity(self.client.prepare_images(views=self.views[:3]), "standard")
        record = {**identity, "state": "submitting", "submission_started": True, "task_id": None}
        barrier = threading.Barrier(2)
        def claim(index):
            barrier.wait(timeout=3)
            try:
                tool.claim_submission(self.root / "jobs" / (str(index) + ".json"), record)
                return True
            except tool.ToolFailure:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(claim, [1, 2])), [False, True])

    def test_crash_between_accepted_journal_and_claim_update_retains_task_id(self):
        save = tool.save_record
        def fail_claim_update(path, record):
            if Path(path).parent.name == "requests" and record.get("task_id"):
                raise OSError("synthetic journal failure")
            save(path, record)
        self.auth()
        self.peer.add("POST", BASE + "/submit-task", {"task_id": "task-1"})
        with mock.patch.object(tool, "save_record", side_effect=fail_claim_update):
            self.assertEqual(self.execute()["task_id"], "task-1")
        self.payload["record_path"] = str(self.root / "jobs/retry.json")
        result = self.execute()
        self.assertEqual(result["task_id"], "task-1")
        self.assertEqual(result["stage"], "journal")
        self.assertEqual(len(self.peer.requests), 2)

    def test_empty_crash_claim_blocks_without_network(self):
        identity = tool.request_identity(self.client.prepare_images(views=self.views[:3]), "standard")
        claim = self.root / "jobs/requests" / (identity["fingerprint"] + ".json")
        claim.parent.mkdir(parents=True)
        claim.write_bytes(b"")
        result = self.execute()
        self.assertEqual(result["stage"], "journal")
        self.assertFalse(self.peer.requests)

    def test_resume_preserves_original_view_fingerprint_and_rejects_other_task(self):
        self.success()
        self.assertTrue(self.execute()["success"])
        path = Path(self.payload["record_path"])
        fingerprint = json.loads(path.read_text())["fingerprint"]
        for view in self.views:
            Path(view["image_path"]).unlink()
        self.payload["arguments"]["task_id"] = "task-1"
        self.success(submit=False, auth=False)
        self.assertTrue(self.execute()["success"])
        self.assertEqual(json.loads(path.read_text())["fingerprint"], fingerprint)
        original = path.read_bytes()
        self.payload["arguments"]["task_id"] = "different-task"
        self.assertEqual(self.execute()["stage"], "journal")
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
