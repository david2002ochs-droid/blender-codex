"""Read live Blender state on the main thread, without changing the scene.

No bpy import happens at module load time, allowing ordinary Python unit tests.
Names and other scene strings are untrusted data, not instructions.
"""

import importlib
import math
import os
from pathlib import Path


SELECTION_INDEX_LIMIT = 2000


def _bpy():
    return importlib.import_module("bpy")


def _vector(value):
    if value is None:
        return None
    # Invalid numeric state must still produce strict JSON-compatible output.
    return [number if math.isfinite(number) else None for number in map(float, value)]


def _object(obj):
    if obj is None:
        return None
    return {
        "name": str(obj.name),
        "type": str(obj.type),
        "location": _vector(getattr(obj, "location", None)),
        "rotation_euler": _vector(getattr(obj, "rotation_euler", None)),
        "scale": _vector(getattr(obj, "scale", None)),
        "dimensions": _vector(getattr(obj, "dimensions", None)),
    }


def _element_selection(elements):
    # Refresh indices after in-session topology edits; no mesh write-back occurs.
    elements.index_update()
    indices = []
    count = 0
    for element in elements:
        if element.select:
            count += 1
            if len(indices) < SELECTION_INDEX_LIMIT:
                indices.append(int(element.index))
    return {"indices": indices, "count": count, "total_count": len(elements),
            "truncated": count > len(indices)}


def _edit_meshes(context):
    if getattr(context, "mode", None) != "EDIT_MESH":
        return []
    objects = getattr(context, "objects_in_mode", None)
    if objects is None:
        active = getattr(context, "active_object", None)
        objects = [active] if active is not None and hasattr(active, "data") else []
    objects = [obj for obj in objects if obj.type == "MESH"]
    if not objects:
        return []
    bmesh = importlib.import_module("bmesh")
    result = []
    for obj in objects:
        mesh = bmesh.from_edit_mesh(obj.data)
        result.append({
            "object_name": str(obj.name), "mesh_name": str(obj.data.name),
            "vertices": _element_selection(mesh.verts),
            "edges": _element_selection(mesh.edges),
            "faces": _element_selection(mesh.faces),
            "index_limit_per_type": SELECTION_INDEX_LIMIT,
        })
    return result


def collect_context(context):
    """Return a JSON snapshot of the actual current (possibly unsaved) scene.

    Pass bpy.context and call on Blender's main thread. No disk reload is used;
    unsaved edits and selection are captured afresh on every invocation.
    """
    bpy = _bpy()
    filepath = str(bpy.data.filepath or "")
    scene = getattr(context, "scene", None)
    unit_settings = getattr(scene, "unit_settings", None)
    return {
        "filepath": filepath,
        "is_unsaved": not bool(filepath),
        "is_dirty": bool(getattr(bpy.data, "is_dirty", False)),
        "scene": None if scene is None else {
            "name": str(scene.name),
            "frame_current": int(scene.frame_current),
            "object_count": len(scene.objects),
            "unit_system": str(getattr(unit_settings, "system", "NONE")),
            "unit_scale": float(getattr(unit_settings, "scale_length", 1.0)),
        },
        "active_object": _object(getattr(context, "active_object", None)),
        "selected_objects": [
            _object(obj) for obj in (getattr(context, "selected_objects", None) or [])
        ],
        "mode": str(getattr(context, "mode", "OBJECT")),
        "edit_meshes": _edit_meshes(context),
        "mesh_select_mode": list(getattr(getattr(context, "tool_settings", None),
                                         "mesh_select_mode", (False, False, False))),
        "process_id": os.getpid(),
    }


def project_directory():
    """Use the existing .blend parent, or the user's existing home directory.

    Never create a directory or use Blender's installation/working directory
    for a scene that has not been saved yet.
    """
    filepath = str(_bpy().data.filepath or "")
    if filepath:
        try:
            parent = Path(filepath).parent
            if Path(filepath).is_absolute() and parent.is_dir():
                return str(parent)
        except (OSError, ValueError):
            pass
    home = Path.home()
    if not home.is_dir():
        raise OSError("User home directory does not exist")
    return str(home)
