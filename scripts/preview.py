"""Open the add-on from this checkout in a fresh Blender window; save no prefs."""
from pathlib import Path
import os
import sys

import bpy
import addon_utils

checkout_root = Path(__file__).resolve().parents[1]
addon_root = Path(os.environ.get('BLENDER_CODEX_PREVIEW_ROOT', checkout_root)).resolve()
sys.path.insert(0, str(addon_root))
official_runtime = Path(os.environ.get('BLENDER_CODEX_OFFICIAL_RUNTIME', checkout_root / '.runtime' / 'official-mcp'))
official_addons = official_runtime / 'source' / 'addon'
sys.path.insert(0, str(official_addons))
addon_utils.enable("blender_mcp_addon", default_set=True)
addon_utils.enable("blender_codex", default_set=True)
bridge_port = os.environ.get('BLENDER_MCP_PORT')
if bridge_port:
    port = int(bridge_port)
    if not 1024 <= port <= 65535:
        raise ValueError('BLENDER_MCP_PORT must be between 1024 and 65535')
    bpy.context.preferences.addons['blender_mcp_addon'].preferences.port = port
codex_executable = os.environ.get('BLENDER_CODEX_EXECUTABLE')
if codex_executable:
    bpy.context.preferences.addons['blender_codex'].preferences.codex_path = codex_executable
bpy.context.preferences.view.show_splash = False
print("BLENDER_CODEX_PREVIEW_READY")


if not bpy.app.background:
    # Auto-connect is owned exclusively by web_ui; no second preview retry loop.

    def record_web_state():
        import json
        from blender_codex import web_ui, _session
        window, area = web_ui._owner()
        def host_state(host):
            if host is None:
                return None
            return {
                "alive": host.alive, "ready": host.ready, "error": host.error,
                "hwnd": host.hwnd, "parent": host.parent_hwnd,
                "geometry": host._geometry,
                "diagnostics": list(getattr(host, "diagnostics", [])),
                "navigation": getattr(host, "navigation", None),
                "visibility": getattr(host, "last_visibility", None),
            }
        receipt = {
            "process_id": os.getpid(),
            "ready": _session.ready,
            "status": _session.status,
            "error": _session.error,
            "timer": bpy.app.timers.is_registered(web_ui._tick),
            "visible": web_ui._visible,
            "host": host_state(web_ui._host),
            "markup_host": host_state(getattr(web_ui, "_markup_host", None)),
            "image_host": host_state(getattr(web_ui, "_image_host", None)),
            "regions": [] if area is None else [
                {"type": r.type, "x": r.x, "y": r.y, "width": r.width,
                 "height": r.height, "category": r.active_panel_category}
                for r in area.regions if r.type in {"UI", "WINDOW"}],
        }
        output = Path(__file__).resolve().parents[1] / ".runtime" / "web-preview-state.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(receipt), encoding="utf-8")
        output.with_name("web-preview-state-%s.json" % os.getpid()).write_text(
            json.dumps(receipt), encoding="utf-8")
        return 2.0

    bpy.app.timers.register(record_web_state, first_interval=2.0)
