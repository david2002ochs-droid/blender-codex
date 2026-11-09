"""Opt-in regression tests for the pinned installed MCP compatibility patch."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "patches" / "apply_blender_mcp_cli_stdin.py"
SOURCE = ROOT / ".runtime" / "official-mcp" / "source" / "mcp" / "blmcp" / "tools_helpers" / "blender_cli.py"


@unittest.skipUnless(SOURCE.is_file(), "prepared pinned official source required")
class CompatibilityPatchTests(unittest.TestCase):
    def call(self, target):
        return subprocess.run([sys.executable, str(SCRIPT), "--file", str(target)], capture_output=True, text=True)

    def test_exact_pinned_helper_and_idempotence_both_line_endings(self):
        original = SOURCE.read_bytes().replace(b"\r\n", b"\n")
        with tempfile.TemporaryDirectory() as folder:
            for newline in (b"\n", b"\r\n"):
                with self.subTest(newline=newline):
                    path = Path(folder) / "blender_cli.py"
                    path.write_bytes(original.replace(b"\n", newline))
                    first = self.call(path)
                    self.assertEqual(first.returncode, 0, first.stderr)
                    record = json.loads(first.stdout)
                    self.assertFalse(record["already_applied"])
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["installed_sha256"])
                    self.assertEqual(path.read_bytes().count(b"stdin=subprocess.DEVNULL"), 1)
                    before = path.read_bytes()
                    second = self.call(path)
                    self.assertEqual(second.returncode, 0, second.stderr)
                    self.assertTrue(json.loads(second.stdout)["already_applied"])
                    self.assertEqual(path.read_bytes(), before)

    def test_modified_patch_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            script = folder / SCRIPT.name
            script.write_bytes(SCRIPT.read_bytes())
            (folder / "blender-mcp-cli-stdin.patch").write_text("unexpected patch", encoding="utf-8")
            target = folder / "blender_cli.py"
            target.write_bytes(SOURCE.read_bytes())
            before = target.read_bytes()
            result = subprocess.run([sys.executable, str(script), "--file", str(target)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("patch file does not match", result.stderr)
            self.assertEqual(target.read_bytes(), before)

    def test_unexpected_installed_contents_are_not_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "blender_cli.py"
            data = SOURCE.read_bytes() + b"\n# unexpected change\n"
            path.write_bytes(data)
            result = self.call(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to patch", result.stderr)
            self.assertEqual(path.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
