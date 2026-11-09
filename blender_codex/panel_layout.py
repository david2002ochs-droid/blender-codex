"""Chat geometry in Blender window coordinates, independent of bpy/Win32."""

import json
import math
from pathlib import Path
import os
import tempfile


def clamp_bounds(bounds, viewport, minimum=(240, 180)):
    x, y, width, height = map(float, bounds)
    left, top, available_width, available_height = map(float, viewport)
    if not all(math.isfinite(v) for v in (x, y, width, height, left, top, available_width, available_height)):
        raise ValueError("Layout values must be finite")
    available_width, available_height = max(1, available_width), max(1, available_height)
    width = min(available_width, max(min(minimum[0], available_width), width))
    height = min(available_height, max(min(minimum[1], available_height), height))
    return tuple(round(v) for v in (min(max(x, left), left + available_width - width),
                                    min(max(y, top), top + available_height - height), width, height))


def normalize(bounds, viewport):
    x, y, w, h = clamp_bounds(bounds, viewport)
    left, top, vw, vh = viewport
    return {"version": 1, "bounds": [(x-left)/max(1,vw), (y-top)/max(1,vh), w/max(1,vw), h/max(1,vh)]}


def restore(value, viewport):
    if not isinstance(value, dict) or value.get("version") != 1 or len(value.get("bounds", [])) != 4:
        raise ValueError("Unsupported layout version")
    x, y, w, h = value["bounds"]
    left, top, vw, vh = viewport
    return clamp_bounds((left+x*vw, top+y*vh, w*vw, h*vh), viewport)


def load(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        restore(value, (0, 0, 1000, 1000))
        return value
    except (OSError, ValueError, TypeError, KeyError):
        return None


def save(path, value):
    restore(value, (0, 0, 1000, 1000))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            name = stream.name
            json.dump(value, stream, allow_nan=False)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def horizontal_bounds(area_left, sidebar_left, right, preferred_width=None, minimum_width=240):
    """Anchor the chat right, permitting a drag across the available viewport.

    None follows Blender's own sidebar edge. An explicit width is constrained
    only by readable minimum and available editor space, including tiny windows.
    """
    available = max(1, right - area_left)
    width = right - sidebar_left if preferred_width is None else preferred_width
    width = min(available, max(min(minimum_width, available), width))
    return right - width, width
