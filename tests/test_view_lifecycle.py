"""Chat-only presentation lifecycle: no running Blender, sockets or model calls."""
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import queue
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class Host:
    instances = []

    def __init__(self, url, **_kwargs):
        self.url, self.alive, self.error = url, True, None
        self.parent_client_size = (1230, 900)
        self.closed, self.hidden = False, True
        self.requested_width = None
        self.instances.append(self)

    def start(self):
        pass

    def update(self, *geometry):
        self.geometry = geometry
        self.hidden = False

    def hide(self):
        self.hidden = True

    def close(self):
        self.closed = True


class Bridge:
    def __init__(self):
        self.commands = queue.Queue()
        self.stopped = False

    def publish(self, _state):
        pass

    def start(self):
        return "http://127.0.0.1:12345/#token=fixture"

    def stop(self):
        self.stopped = True


class ViewLifecycleTests(unittest.TestCase):
    def setUp(self):
        Host.instances.clear()
        self.package = ModuleType("view_lifecycle_fixture")
        self.package.__path__ = [str(ROOT / "blender_codex")]
        self.client = NS(close=Mock(), interrupt=Mock())
        self.session = NS(client=self.client, busy=True, ready=True, generation=77, resources=object(), error="", image_markup=None)
        self.package._session = self.session
        self.package._preferences = lambda _context: NS()
        self.sidebar = NS(type="UI", x=800, y=0, width=430, height=850, active_panel_category="Codex")
        self.region = NS(type="WINDOW", x=0, y=0, width=1230, height=850)
        self.area = NS(type="VIEW_3D", x=0, y=0, width=1230, height=850,
                       spaces=NS(active=NS(show_region_ui=True)), regions=[self.sidebar, self.region],
                       as_pointer=lambda: 22, tag_redraw=Mock())
        self.window = NS(width=1230, height=900, screen=NS(areas=[self.area]), as_pointer=lambda: 11)
        self.context = NS(window=self.window, area=self.area,
                          preferences=NS(system=NS(ui_scale=1)), temp_override=lambda **_kw: nullcontext())
        self.registered = set()
        timers = NS(is_registered=lambda fn: fn in self.registered,
                    register=lambda fn, **_kw: self.registered.add(fn), unregister=lambda fn: self.registered.discard(fn))
        self.draw = Mock(return_value={"FINISHED"})
        self.draw.poll.return_value = True
        ops = NS(**{name: self.draw if name == "draw" else Mock() for name in ("connect", "disconnect", "new_chat", "send", "stop", "draw")})
        self.bpy = NS(app=NS(background=False, timers=timers), context=self.context,
                      data=NS(window_managers=[NS(windows=[self.window])]), ops=NS(codex_chat=ops))
        modules = {self.package.__name__: self.package, "bpy": self.bpy,
                   self.package.__name__ + ".web_bridge": NS(WebBridge=Bridge),
                   self.package.__name__ + ".web_host": NS(WebHost=Host)}
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        name = self.package.__name__ + ".web_ui"
        spec = importlib.util.spec_from_file_location(name, ROOT / "blender_codex/web_ui.py")
        self.ui = importlib.util.module_from_spec(spec)
        sys.modules[name] = self.ui
        spec.loader.exec_module(self.ui)
        self.ui._layout_loaded = True
        self.ui._snapshot = lambda _context: {}
        self.minimized = False
        self.ui._window_is_minimized = lambda: self.minimized
        self.addCleanup(self.ui.close)

    def open(self):
        self.ui.open_panel(self.context)
        self.ui._tick()

    def test_only_chat_created_no_permanent_markup_surface(self):
        self.open()
        self.assertEqual(len(Host.instances), 1)
        self.assertNotIn("surface=markup", Host.instances[0].url)
        self.assertNotIn("_markup_host", self.ui.__dict__)
        self.ui._action({"action": "draw"}, self.context)
        self.draw.assert_called_once()

    def test_os_minimize_restore_preserves_busy_agent_and_bridge(self):
        self.open()
        host, bridge = self.ui._host, self.ui._bridge
        self.assertFalse(host.hidden)
        self.minimized = True
        self.assertEqual(self.ui._tick(), .2)
        self.assertTrue(host.hidden)
        self.assertIs(self.ui._bridge, bridge)
        self.assertTrue(self.session.busy)
        self.assertEqual(self.session.generation, 77)
        self.client.close.assert_not_called()
        self.client.interrupt.assert_not_called()
        self.minimized = False
        self.ui._tick()
        self.assertIs(self.ui._host, host)
        self.assertFalse(host.hidden)

    def test_file_view_reset_does_not_disconnect_agent(self):
        self.open()
        old_bridge, old_host = self.ui._bridge, self.ui._host
        self.ui.reset_for_file_load()
        self.assertTrue(old_bridge.stopped and old_host.closed)
        self.assertIs(self.session.client, self.client)
        self.assertTrue(self.session.busy)
        self.client.close.assert_not_called()
        self.client.interrupt.assert_not_called()

    def test_explicit_image_editor_retained(self):
        self.open()
        self.session.image_markup = {"id": "explicit-image"}
        self.ui._tick()
        self.assertEqual(len(Host.instances), 2)
        self.assertIn("surface=image-editor", Host.instances[1].url)

    def test_cleanup_closes_legacy_toolbar_without_creating_replacement(self):
        legacy = Host("legacy-toolbar")
        self.ui._markup_host = legacy
        self.open()
        self.assertTrue(legacy.closed)
        self.assertNotIn("_markup_host", self.ui.__dict__)
        self.assertEqual(len(Host.instances), 2)  # old fixture + single new chat

    def test_idle_settings_reconnect_internally_without_turn_submission(self):
        prefs = NS(codex_path="old", mcp_command="old", mcp_args="[]")
        self.package._preferences = lambda _ctx: prefs
        self.session.busy = False
        self.client._busy = False
        def disconnect(**_kwargs):
            self.session.client = None
            self.session.ready = False
        self.package._disconnect = Mock(side_effect=disconnect)
        result = self.ui._action({"action":"settings", "codex_path":"new", "mcp_command":"mcp", "mcp_args":"[]"}, self.context)
        self.assertTrue(result["ok"])
        self.assertEqual(prefs.codex_path, "new")
        self.package._disconnect.assert_called_once()
        self.ui._registered = True
        self.ui._autoconnect_tick()
        self.bpy.ops.codex_chat.connect.assert_called_once()
        self.bpy.ops.codex_chat.send.assert_not_called()

    def test_busy_settings_keep_existing_connection(self):
        with self.assertRaises(ValueError):
            self.ui._action({"action":"settings"}, self.context)
        self.client.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
