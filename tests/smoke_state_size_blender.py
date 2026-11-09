"""Actual Blender UI tick with >4 MiB input; fake native host, no user scene."""
from contextlib import nullcontext
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
import blender_codex as addon
from blender_codex import web_ui as ui
from blender_codex.web_bridge import WebBridge
assert Path(ui.__file__).resolve().is_relative_to(ROOT / "blender_codex")


class Host:
    alive = True
    closed = False
    error = None
    parent_client_size = (1230, 900)
    requested_width = None
    def update(self, *_args):
        pass
    def hide(self):
        pass
    def close(self):
        self.closed = True


bridge, host = WebBridge(), Host()
sidebar = NS(type="UI", x=800, y=0, width=430, height=850, active_panel_category="Codex")
region = NS(type="WINDOW", x=0, y=0, width=1230, height=850)
area = NS(type="VIEW_3D", x=0, y=0, width=1230, height=850, regions=[sidebar, region], spaces=NS(active=NS(show_region_ui=True)))
window = NS(width=1230, height=900)
context = NS(preferences=NS(system=NS(ui_scale=1)), temp_override=lambda **kwargs: nullcontext())
fake_bpy = NS(context=context, app=NS(timers=bpy.app.timers))
text = "large observed output " * 150000
snapshot = {"ready": True, "busy": False, "messages": [], "tool_calls": [
    {"id": "tool", "seq": 1, "status": "completed", "result": text, "content": [{"type": "text", "text": text}]}]}
with patch.object(ui, "bpy", fake_bpy), patch.object(ui, "_owner", return_value=(window, area)), patch.object(ui, "_snapshot", return_value=snapshot):
    previous = ui._bridge, ui._host, ui._visible
    ui._bridge, ui._host, ui._visible = bridge, host, True
    try:
        assert ui._tick() == 0.1
        assert not host.closed and ui._bridge is bridge
        assert len(bridge._state) <= 4 * 1024 * 1024
        assert ui._tick() == 0.1
        assert not host.closed
        print("LARGE_STATE_TIMER_PASS: >4 MiB input, bounded state, hosts retained, next tick works")
    finally:
        ui._bridge, ui._host, ui._visible = previous
        addon._session.resources.close()
