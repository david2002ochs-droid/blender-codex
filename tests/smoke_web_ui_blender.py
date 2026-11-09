"""UI lifecycle with real Blender registration and fake native hosts; no network/model calls.

Run: blender --background --factory-startup --python tests/smoke_web_ui_blender.py
"""
from contextlib import nullcontext
from pathlib import Path
import queue
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
from unittest.mock import patch

import addon_utils
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import blender_codex as addon
from blender_codex import web_ui as ui, web_bridge, web_host
from blender_codex import context as context_module, annotations, scene_lifecycle
assert Path(addon.__file__).resolve().is_relative_to(ROOT := Path(__file__).resolve().parents[1] / "blender_codex")
assert Path(ui.__file__).resolve().is_relative_to(ROOT)

captures = tempfile.TemporaryDirectory(prefix="web-lifecycle-capture-")
capture_path = Path(captures.name) / "view.png"
capture_path.write_bytes(b"\x89PNG\r\n\x1a\nfixture-image")


class Bridge:
    instances = []

    def __init__(self):
        self.commands = queue.Queue()
        self.stopped = False
        self.instances.append(self)

    def publish(self, _value):
        pass

    def start(self):
        return "http://127.0.0.1:12345/#token=test-fixture"

    def stop(self):
        self.stopped = True


class Host:
    instances = []

    def __init__(self, url):
        self.url = url
        self.alive = True
        self.error = None
        self.closed = False
        self.hidden = True
        self.geometry = None
        self.parent_client_size = (1230, 900)
        self.instances.append(self)

    def start(self):
        pass

    def hide(self):
        self.hidden = True

    def update(self, *geometry):
        self.hidden = False
        self.geometry = geometry

    def close(self):
        self.closed = True


assert addon_utils.enable("blender_codex", default_set=True) is not None
try:
    assert bpy.app.timers.is_registered(ui._watch_tabs)
    assert addon._session.client is None
    assert addon.hi3d_ui.HI3D_PT_panel.bl_category == "3D Providers"
    with patch.object(web_host, "WebHost", side_effect=AssertionError("Headless GUI launch")):
        ui._watch_tabs()
        assert ui._host is None and "_markup_host" not in ui.__dict__
        try:
            ui.open_panel(bpy.context)
            raise AssertionError("Explicit headless open must be rejected")
        except RuntimeError as exc:
            assert "sichtbares Blender-Fenster" in str(exc)

    class DeferredSidebar(NS):
        def __setattr__(self, name, value):
            if name == "active_panel_category" and self.__dict__.get("readonly_ticks", 0):
                self.__dict__["readonly_ticks"] -= 1
                raise AttributeError("active_panel_category is read-only before first draw")
            super().__setattr__(name, value)

    sidebar = DeferredSidebar(type="UI", width=1, height=850, x=800, y=0,
                              active_panel_category="Item", readonly_ticks=2)
    # Deliberately overlap WINDOW with sidebar: geometry must still clip at x=800.
    region = NS(type="WINDOW", x=0, y=0, width=1230, height=850)
    tools = NS(type="TOOLS", x=0, width=40)
    space = NS(show_region_ui=False, show_region_toolbar=True)
    area = NS(type="VIEW_3D", x=0, y=0, width=1230, height=850, spaces=NS(active=space),
              regions=[sidebar, region, tools], as_pointer=lambda: 22, tag_redraw=lambda: None)
    window = NS(width=1230, height=900, as_pointer=lambda: 11, screen=NS(areas=[area]))
    state = NS(input_text="", include_view=False)
    context = NS(window=window, area=area, window_manager=NS(codex_chat=state),
                 preferences=NS(system=NS(ui_scale=1), addons={}), temp_override=lambda **_kw: nullcontext())
    fake_bpy = NS(app=NS(background=False, timers=bpy.app.timers), context=context,
                  data=NS(window_managers=[NS(windows=[window])]))
    sent = []

    class Operator:
        def __init__(self, name):
            self.name = name

        def poll(self):
            return not addon._session.busy if self.name == "send" else True

        def __call__(self):
            if self.name == "send":
                sent.append((state.input_text, state.include_view))
                addon._session.busy = True
            return {"FINISHED"}

    fake_bpy.ops = NS(codex_chat=NS(**{name: Operator(name) for name in
                                     ("connect", "disconnect", "new_chat", "send", "stop", "draw")}))
    with patch.object(ui, "bpy", fake_bpy), patch.object(ui, "_snapshot", return_value={}), \
            patch.object(web_bridge, "WebBridge", Bridge), patch.object(web_host, "WebHost", Host), \
            patch.object(context_module, "collect_context", return_value={"process_id": 0}), \
            patch.object(context_module, "project_directory", return_value=addon._session.project_root), \
            patch.object(scene_lifecycle, "bind_turn", return_value={}), \
            patch.object(annotations, "capture_view", return_value=str(capture_path)), \
            patch.object(annotations, "view_metadata", return_value={}):
        ui._watch_tabs()
        assert space.show_region_ui and not Host.instances  # Wait for real region size.
        sidebar.width = 430
        assert ui._watch_tabs() == 0.2
        assert ui._watch_tabs() == 0.2
        assert not Host.instances and ui._startup_attempts == 2
        ui._watch_tabs()
        ui._tick()
        assert sidebar.active_panel_category == "Codex"
        assert len(Bridge.instances) == 1 and len(Host.instances) == 1
        assert "surface=markup" not in Host.instances[0].url
        assert "_markup_host" not in ui.__dict__
        assert not Host.instances[0].hidden
        x, _y, width, height = Host.instances[0].geometry
        assert x >= sidebar.x and width > 0 and height == sidebar.height
        for _ in range(4):
            ui._watch_tabs()
            ui._tick()
        assert len(Host.instances) == 1 and addon._session.client is None

        addon._session.ready = True
        class Transport:
            _lock = threading.Lock()
            _ready = True
            _closing = False
            _busy = False
            def send(self, text, scene_context, image_paths=None, attachment_texts=None):
                assert scene_context["process_id"] == 0
                assert all(Path(path).is_file() for path in image_paths or [])
                sent.append((text, bool(image_paths)))
                self._busy = True
                return True
            def close(self):
                self._busy = False
        addon._session.client = Transport()
        ui._action({"action": "send", "text": "Comment from toolbar", "include_view": True}, context)
        assert sent == [("Comment from toolbar", True)]
        try:
            ui._action({"action": "send", "text": "Overlapping sidebar send", "include_view": False}, context)
            raise AssertionError("Overlapping turns accepted")
        except ValueError:
            pass
        addon._session.busy = False

        ui._action({"action": "hide_panel"}, context)
        for _ in range(3):
            ui._watch_tabs()
            ui._tick()
        assert all(host.hidden for host in Host.instances)
        assert len(Host.instances) == 1 and ui.panel_status(context) == "minimized"
        ui.reset_for_file_load()
        ui._watch_tabs()
        assert len(Host.instances) == 1  # Panel minimization survives file view reset.
        sidebar.active_panel_category = "Item"
        ui._watch_tabs()
        sidebar.active_panel_category = "Codex"
        ui._watch_tabs()
        ui._tick()
        assert len(Bridge.instances) == 2 and len(Host.instances) == 2
        ui.reset_for_file_load()
        ui._watch_tabs()
        ui._tick()
        assert len(Host.instances) == 3  # File view rebuild opens only the chat.
        ui._host.alive = False
        ui._tick()
        assert ui.panel_status(context) == "error"
        for _ in range(3):
            ui._watch_tabs()
        assert len(Host.instances) == 3  # No crash/relaunch loop.
        ui.open_panel(context)
        ui._tick()
        assert len(Host.instances) == 4
        ui.unregister()
        assert all(host.closed for host in Host.instances)
        assert all(bridge.stopped for bridge in Bridge.instances)
        assert not bpy.app.timers.is_registered(ui._watch_tabs)
        assert not bpy.app.timers.is_registered(ui._tick)
finally:
    addon_utils.disable("blender_codex", default_set=True)
    captures.cleanup()

assert not hasattr(bpy.types.WindowManager, "codex_chat")
print("WEB_UI_LIFECYCLE_PASS: headless guard, startup wait, one chat/no permanent markup, shared turn guard, panel minimize, view reset, retry, cleanup")
