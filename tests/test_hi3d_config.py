"""Credential-source isolation with synthetic values only; no provider traffic."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender_codex"))
import hi3d_config as config
from native_tools import NativeTools


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env_file = self.root / ".env"
        self.env_file.write_text('HI3D_CLIENT_ID="fixture-ak"\nHI3D_CLIENT_SECRET="fixture-sk"\n', encoding="utf-8")

    def load(self, **kwargs):
        return config.load_credentials(cwd=self.root, environ={}, **kwargs)

    def test_local_file_read_does_not_export_keys(self):
        before = dict(os.environ)
        self.assertEqual(self.load(), ("fixture-ak", "fixture-sk"))
        self.assertEqual(dict(os.environ), before)

    def test_quoted_values_are_literal_including_special_characters(self):
        self.env_file.write_text('\ufeffexport HI3D_CLIENT_ID="ak-$LITERAL" # comment\n'
                                 "HI3D_CLIENT_SECRET='sk+/==#${NOT_EXPANDED}\\path'\n", encoding="utf-8")
        self.assertEqual(self.load(), ("ak-$LITERAL", "sk+/==#${NOT_EXPANDED}\\path"))

    def test_environment_pair_overrides_dotenv(self):
        self.assertEqual(config.load_credentials(cwd=self.root, environ={
            "HI3D_CLIENT_ID": "env-ak", "HI3D_CLIENT_SECRET": "env-sk"}), ("env-ak", "env-sk"))

    def test_explicit_pair_overrides_environment_and_file(self):
        self.assertEqual(config.load_credentials(explicit=("panel-ak", "panel-sk"), cwd=self.root,
                         environ={"HI3D_CLIENT_ID": "env-ak"}), ("panel-ak", "panel-sk"))
        self.assertEqual(self.load(explicit=("", "")), ("", ""))

    def test_partial_sources_are_not_combined(self):
        with self.assertRaises(ValueError):
            config.load_credentials(cwd=self.root, environ={"HI3D_CLIENT_ID": "other-ak"})
        with self.assertRaises(ValueError):
            self.load(explicit=("other-ak", ""))
        self.env_file.write_text('HI3D_CLIENT_ID="file-ak"\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.load()

    def test_selected_missing_file_does_not_silently_fallback(self):
        with self.assertRaises(ValueError):
            self.load(env_file=self.root / "missing.env")

    def test_selected_file_via_environment(self):
        other = self.root / "selected.env"
        other.write_text('HI3D_CLIENT_ID=selected-ak\nHI3D_CLIENT_SECRET=selected-sk\n')
        self.assertEqual(config.load_credentials(cwd=self.root, environ={"HI3D_ENV_FILE": "selected.env"}),
                         ("selected-ak", "selected-sk"))

    def test_invalid_quotes_and_duplicates_do_not_echo_values(self):
        for text in ('HI3D_CLIENT_SECRET="NEVER_ECHO_THIS\n',
                     'HI3D_CLIENT_ID=NEVER_ECHO_THIS\nHI3D_CLIENT_ID=other\n'):
            self.env_file.write_text(text)
            with self.assertRaises(ValueError) as raised:
                self.load()
            self.assertNotIn("NEVER_ECHO_THIS", str(raised.exception))

    def test_source_checkout_fallback_for_unsaved_scene(self):
        with tempfile.TemporaryDirectory() as empty, patch.object(config, "SOURCE_ROOT", self.root):
            self.assertEqual(config.load_credentials(cwd=empty, environ={}), ("fixture-ak", "fixture-sk"))

    def test_same_native_runner_rereads_file_without_provider_calls(self):
        self.env_file.write_text('HI3D_CLIENT_ID=""\nHI3D_CLIENT_SECRET=""\n')
        runner = NativeTools(self.root / "jobs", cwd=self.root, env_file=self.env_file)
        args = {"image_path": str(self.root / "nonexistent.png")}
        clean_environment = {key: value for key, value in os.environ.items() if not key.startswith("HI3D_")}
        with patch.dict(os.environ, clean_environment, clear=True):
            self.assertEqual(runner.call("hi3d_image_to_3d", args, threading.Event())["stage"], "config")
            self.env_file.write_text('HI3D_CLIENT_ID="fixture-ak"\nHI3D_CLIENT_SECRET="fixture-sk"\n')
            # Input is rejected before authentication, so no API traffic occurs.
            self.assertEqual(runner.call("hi3d_image_to_3d", args, threading.Event())["stage"], "input")


if __name__ == "__main__":
    unittest.main()
