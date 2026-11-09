import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("official_backend_under_test", ROOT / "blender_codex/official_backend.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OfficialBackendTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def prepare(self, **changes):
        python = module.runtime_python(self.root)
        python.parent.mkdir(parents=True)
        python.touch()
        record = {"source_url": module.SOURCE_URL, "revision": module.SOURCE_REVISION}
        record.update(changes)
        (self.root / "installation.json").write_text(json.dumps(record), encoding="utf-8-sig")
        return python

    def test_default_is_official_pinned_source_with_no_community_fallback(self):
        python = self.prepare()
        command, args = module.resolve_launch(runtime_root=self.root)
        self.assertEqual(command, str(python))
        self.assertEqual(args, ["-m", "blmcp", "--transport", "stdio"])
        self.assertEqual(module.SOURCE_URL, "https://projects.blender.org/lab/blender_mcp.git")
        self.assertEqual(len(module.SOURCE_REVISION), 40)
        self.assertEqual(module.SOURCE_LICENSE, "GPL-3.0-or-later")

    def test_missing_installation_reports_setup_without_installing(self):
        with self.assertRaises(module.OfficialBackendError) as caught:
            module.resolve_launch(runtime_root=self.root)
        self.assertIn("setup-official-mcp.ps1", str(caught.exception))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_foreign_or_wrong_revision_manifest_is_rejected(self):
        self.prepare(revision="f" * 40)
        with self.assertRaises(module.OfficialBackendError):
            module.resolve_launch(runtime_root=self.root)
        (self.root / "installation.json").write_text(json.dumps(
            {"revision": module.SOURCE_REVISION, "source_url": "https://unverified.example/server"}))
        with self.assertRaises(module.OfficialBackendError):
            module.resolve_launch(runtime_root=self.root)

    def test_explicit_settings_and_existing_codex_configuration_preserved(self):
        self.assertEqual(module.resolve_launch("", []), ("", []))
        args = ["--directory", "C:/official checkout/mcp", "run", "blender-mcp", "--transport", "stdio"]
        self.assertEqual(module.resolve_launch("uv", args), ("uv", args))
        self.assertEqual(args[0], "--directory")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_default_arguments_are_not_shared_mutable_state(self):
        self.prepare()
        _, args = module.resolve_launch(runtime_root=self.root)
        args.append("changed")
        self.assertEqual(module.resolve_launch(runtime_root=self.root)[1], list(module.DEFAULT_MCP_ARGS))

    def test_invalid_arguments_fail_before_process_start(self):
        for args in ("-m blmcp", [1], {}):
            with self.assertRaises(module.OfficialBackendError):
                module.resolve_launch("custom-python", args)


if __name__ == "__main__":
    unittest.main()
