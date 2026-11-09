import importlib.util
from pathlib import Path
from types import SimpleNamespace
import socket
import unittest

spec = importlib.util.spec_from_file_location("target_under_test", Path(__file__).resolve().parents[1] / "blender_codex/blender_target.py")
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class BlenderTargetTests(unittest.TestCase):
    def test_actual_listener_wins_over_stale_preferences(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            addon = SimpleNamespace(preferences=SimpleNamespace(host="localhost", port=9876))
            module = SimpleNamespace(mcp_to_blender_server=SimpleNamespace(_state=SimpleNamespace(sock=listener)))
            env = target.target_environment({"blender_mcp_addon": addon}, {"blender_mcp_addon": module})
            self.assertEqual(env, {"BLENDER_MCP_HOST": "127.0.0.1", "BLENDER_MCP_PORT": str(listener.getsockname()[1])})

    def test_failed_own_start_never_falls_back_to_foreign_default_listener(self):
        # Another process listening at 9876 is irrelevant: own socket is absent.
        module = SimpleNamespace(mcp_to_blender_server=SimpleNamespace(_state=SimpleNamespace(sock=None)))
        addon = SimpleNamespace(preferences=SimpleNamespace(host="localhost", port=9876))
        with self.assertRaisesRegex(ValueError, "this Blender instance"):
            target.target_environment({"blender_mcp_addon": addon}, {"blender_mcp_addon": module})
        with self.assertRaises(ValueError):
            target.target_environment({}, {})

    def test_extension_namespace_supported_but_multiple_own_listeners_rejected(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            module = SimpleNamespace(mcp_to_blender_server=SimpleNamespace(_state=SimpleNamespace(sock=listener)))
            name = "bl_ext.blender_lab.mcp"
            self.assertEqual(target.target_environment({name: object()}, {name: module})["BLENDER_MCP_PORT"], str(listener.getsockname()[1]))
            with self.assertRaises(ValueError):
                target.target_environment({name: object(), "blender_mcp_addon": object()}, {name: module, "blender_mcp_addon": module})
