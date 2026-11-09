"""Native annotation hooks, called exclusively from Blender's UI main thread.

Capture includes the whole 3D editor (sidebar/header included), as displayed,
including visible annotations and overlays. Nothing is rendered separately,
deleted, or sent to any service here. The UI owns explicit image-send consent.
"""

import importlib
from pathlib import Path
import tempfile
import threading


def _markup():
    if __package__:
        return importlib.import_module(".markup", __package__)
    # Standalone tests avoid importing the bpy-dependent add-on entry point.
    from importlib import util
    import sys
    key = "_blender_codex_markup"
    if key not in sys.modules:
        spec = util.spec_from_file_location(key, Path(__file__).with_name("markup.py"))
        module = util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


def _viewport(context):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Annotation functions require Blender's UI main thread")
    bpy = importlib.import_module("bpy")
    if bpy.app.background:
        raise RuntimeError("Viewport annotations/capture require Blender's graphical UI; background mode is unsupported")
    window = getattr(context, "window", None)
    if window is None:
        raise RuntimeError("No Blender window available for viewport capture")
    area = getattr(context, "area", None)
    if area is None or area.type != "VIEW_3D":
        area = next((area for area in window.screen.areas if area.type == "VIEW_3D"), None)
    if area is None:
        raise RuntimeError("Open a 3D Viewport before using annotations or capture")
    region = next((region for region in area.regions if region.type == "WINDOW"), None)
    if region is None:
        raise RuntimeError("The 3D Viewport has no visible window region")
    return bpy, window, area, region


def activate_draw(context):
    """Begin a cancellable native annotation operation on owned temporary data."""
    bpy, window, area, region = _viewport(context)
    return _markup().activate(context, bpy, window, area, region)


def cancel_draw(context=None):
    return _markup().cancel_draw(context)


def is_drawing(context):
    return _markup().is_drawing(context)


def register():
    _markup().register()


def unregister():
    _markup().unregister()


def capture_view(context):
    """Return an absolute PNG path of the visible 3D editor, overlays included.

    Each capture has its own temporary directory. The caller may remove its
    capture after transport finishes; user annotations are never changed.
    """
    bpy, window, area, region = _viewport(context)
    path = Path(tempfile.mkdtemp(prefix="blender_codex_view_")) / "viewport.png"
    try:
        with context.temp_override(window=window, area=area, region=region):
            result = bpy.ops.screen.screenshot_area(
                filepath=str(path), hide_props_region=False, check_existing=False)
        if "FINISHED" not in result or not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("Blender did not create the viewport screenshot")
    except Exception:
        # Only remove files allocated by this invocation, never user data.
        if path.exists():
            path.unlink()
        path.parent.rmdir()
        raise
    return str(path.resolve())


def view_metadata(context):
    """Describe the captured editor and the active viewport's projection."""
    _bpy, _window, area, region = _viewport(context)
    space = area.spaces.active
    region_data = (getattr(context, "region_data", None)
                   if getattr(context, "area", None) == area else None)
    view = region_data or space.region_3d
    if view is None:
        raise RuntimeError("3D viewport projection data is unavailable")

    def matrix(value):
        return [[float(component) for component in row] for row in value]

    return {
        "capture_scope": "whole_3d_editor_including_sidebar_and_header",
        "view_matrix": matrix(view.view_matrix),
        "projection_matrix": matrix(view.window_matrix),
        "perspective_matrix": matrix(view.perspective_matrix),
        "view_perspective": str(view.view_perspective),
        "is_perspective": bool(view.is_perspective),
        "region_size": [int(region.width), int(region.height)],
        "region_offset_in_editor": [int(region.x - area.x), int(region.y - area.y)],
        "editor_size": [int(area.width), int(area.height)],
        "overlays_visible": bool(space.overlay.show_overlays),
        "annotations_visible": bool(space.overlay.show_annotation),
    }
