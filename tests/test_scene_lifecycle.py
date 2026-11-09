"""File-boundary guards preserve the agent while rejecting stale scene code."""
from collections import namedtuple
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scene_lifecycle_under_test", ROOT / "blender_codex/scene_lifecycle.py")
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)
Result = namedtuple("Result", "response check_fn", defaults=[None])


class SceneLifecycleTests(unittest.TestCase):
    def setUp(self):
        lifecycle._records.clear()
        lifecycle._loading = lifecycle._invalidated = False
        lifecycle._turn_epoch = None
        self.calls = []
        self.stops = self.starts = 0
        self.pending = ["old socket", "old deferred response"]
        self.server = NS(_state=NS(sock=NS(getsockname=lambda: ("127.0.0.1", 19876))), _ExecResult=Result)

        def execute(code, strict_json):
            self.calls.append(code)
            if code == "deferred":
                return Result({"status": "ok"}, lambda: self.calls.append("deferred check") or {"status": "ok"})
            return Result({"status": "ok", "result": {"code": code}})

        def stop():
            self.stops += 1
            self.pending.clear()
            self.server._state.sock = None

        def start(host, port):
            self.starts += 1
            self.server._state.sock = NS(getsockname=lambda: (host, port))

        self.server._execute_code = self.original = execute
        self.server.stop, self.server.start = stop, start
        self.server.is_running = lambda: self.server._state.sock is not None
        lifecycle.install({"blender_mcp_addon": None}, {"blender_mcp_addon": NS(mcp_to_blender_server=self.server)})
        self.context = NS(scene=NS(as_pointer=lambda: 101))
        self.addCleanup(lifecycle.unregister)

    def test_old_turn_rejected_after_two_unsaved_documents_same_process(self):
        old = lifecycle.bind_turn(self.context)
        self.assertEqual(self.server._execute_code("old scene change", False).response["status"], "ok")
        lifecycle.before_file_load()
        self.assertFalse(self.pending)
        self.assertEqual(self.server._execute_code("during load", False).response["code"], "scene_target_changed")
        lifecycle.after_file_load()
        self.context.scene = NS(as_pointer=lambda: 202)
        stale = self.server._execute_code("must not reach new scene", False)
        self.assertEqual(stale.response["code"], "scene_target_changed")
        self.assertEqual(self.calls, ["old scene change"])
        fresh = lifecycle.bind_turn(self.context)
        self.assertNotEqual(old["scene_epoch"], fresh["scene_epoch"])
        self.assertEqual(fresh["scene_identity"], 202)
        self.assertEqual(self.server._execute_code("new explicit turn", False).response["status"], "ok")
        self.assertEqual(self.stops, 2)  # load boundary + fresh-turn queue flush

    def test_old_deferred_callback_stays_blocked_after_fresh_bind(self):
        lifecycle.bind_turn(self.context)
        deferred = self.server._execute_code("deferred", False).check_fn
        lifecycle.before_file_load()
        lifecycle.after_file_load()
        lifecycle.bind_turn(self.context)
        self.assertEqual(deferred()["code"], "scene_target_changed")
        self.assertNotIn("deferred check", self.calls)

    def test_bind_during_load_is_rejected(self):
        lifecycle.before_file_load()
        with self.assertRaisesRegex(RuntimeError, "finish loading"):
            lifecycle.bind_turn(self.context)

    def test_duplicate_pre_is_idempotent(self):
        lifecycle.before_file_load()
        epoch = lifecycle.target_context(self.context)["scene_epoch"]
        lifecycle.before_file_load()
        self.assertEqual(lifecycle.target_context(self.context)["scene_epoch"], epoch)
        self.assertEqual(self.stops, 1)

    def test_unavailable_listener_does_not_fall_back(self):
        self.server.stop()
        with self.assertRaisesRegex(RuntimeError, "exactly one guarded"):
            lifecycle.bind_turn(self.context)

    def test_replaced_guard_is_rejected(self):
        self.server._execute_code = lambda *_args: Result({"status": "ok"})
        with self.assertRaisesRegex(RuntimeError, "guard was replaced"):
            lifecycle.install({"blender_mcp_addon": None}, {"blender_mcp_addon": NS(mcp_to_blender_server=self.server)})

    def test_blender_addon_collection_uses_named_items_not_value_iteration(self):
        class Addons:
            def __iter__(self):
                return iter([NS(module="blender_mcp_addon")])
            def items(self):
                return [("blender_mcp_addon", NS())]
        lifecycle.install(Addons(), {"blender_mcp_addon": NS(mcp_to_blender_server=self.server)})
        self.assertEqual(len(lifecycle._records), 1)

    def test_unregister_restores_original_executor(self):
        lifecycle.unregister()
        self.assertIs(self.server._execute_code, self.original)


if __name__ == "__main__":
    unittest.main()
