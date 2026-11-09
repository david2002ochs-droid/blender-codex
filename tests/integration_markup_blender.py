"""Real Blender annotation data ownership; factory startup only, no user file I/O.

UI tool/modal dispatch is checked separately with fakes and by the coordinator's
visible preview. This headless check deliberately does not claim a real keypress.
"""
from contextlib import nullcontext
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import bpy

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_markup_test", root / "blender_codex/markup.py")
markup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(markup)
scene = bpy.context.scene
assert not bpy.data.filepath
original = bpy.data.annotations.new("Existing user notes")
scene.annotation = original
user_layer = original.layers.new("Original user layer", set_active=True)
frame = user_layer.frames.new(1)
stroke = frame.strokes.new()
stroke.points.add(count=2)
stroke.points[0].co = (1, 2, 3)
stroke.points[1].co = (4, 5, 6)
original_active = (original.layers.active_index, original.layers.active_note)
tool_calls = []
area = NS(type="VIEW_3D", tag_redraw=lambda: None)
window = NS(screen=NS(areas=[area]))
context = NS(scene=scene, window=window, area=area, window_manager=NS(),
             temp_override=lambda **_kw: nullcontext())

def tool_set(**values):
    tool_calls.append(values)
    return {"FINISHED"}

test_bpy = NS(data=bpy.data, ops=NS(wm=NS(tool_set_by_id=tool_set)))
session = markup._begin(context, test_bpy, window, area, NS(), "builtin.move")
assert scene.annotation != original
assert len(scene.annotation.layers) == 2
assert scene.annotation.layers[0].lock and not user_layer.lock
owned_frame = session.layer.frames.new(1)
owned_stroke = owned_frame.strokes.new()
owned_stroke.points.add(count=1)
owned_stroke.points[0].co = (9, 9, 9)
temporary_name = scene.annotation.name
assert markup.is_drawing(context)
assert markup.cancel_draw(context)
assert scene.annotation == original
assert (original.layers.active_index, original.layers.active_note) == original_active
assert tuple(user_layer.frames[0].strokes[0].points[0].co) == (1, 2, 3)
assert len(original.layers) == 1 and not user_layer.lock
assert temporary_name not in bpy.data.annotations
assert tool_calls == [{"name": "builtin.move", "space_type": "VIEW_3D"}]
markup.register(bpy)
assert bpy.ops.codex_markup.escape_guard.get_rna_type().identifier == "CODEX_MARKUP_OT_escape_guard"
markup.unregister()
assert not bpy.data.filepath
print("NATIVE_MARKUP_DATA_PASS: original native strokes/active layer/locks preserved; owned data removed; previous tool requested; operator registration cleaned")
