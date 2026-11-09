"""Operation-scoped native annotation ownership and Escape observer.

No bpy access occurs on import or worker threads. A temporary COPY of the
annotation data displays prior user strokes without ever editing their data.
Only the current operation's copy is discarded on cancel.
"""
import importlib
import threading
from types import SimpleNamespace
import uuid

_draw = None
_operator_class = None


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Markup operations require Blender's main thread")


def _pointer(value):
    return value.as_pointer() if hasattr(value, "as_pointer") else id(value)


def _owner(context, session):
    window = getattr(context, "window", None)
    area = getattr(context, "area", None)
    return (window is not None and area is not None
            and _pointer(window) == session.window_id and _pointer(area) == session.area_id)


def _annotation_api(bpy, scene):
    if hasattr(scene, "annotation") and hasattr(bpy.data, "annotations"):
        return "annotation", bpy.data.annotations
    if hasattr(scene, "grease_pencil") and hasattr(bpy.data, "grease_pencils"):
        return "grease_pencil", bpy.data.grease_pencils
    raise RuntimeError("This Blender version does not expose native scene annotations")


def _begin(context, bpy, window, area, region, previous_tool):
    """Allocate operation-owned native data; used by isolated Blender tests too."""
    global _draw
    scene = context.scene
    attribute, collection = _annotation_api(bpy, scene)
    original = getattr(scene, attribute)
    token = uuid.uuid4().hex
    temporary = original.copy() if original is not None else collection.new("Codex markup " + token[:8])
    try:
        temporary.name = "Codex markup " + token[:8]
        # Lock copies of old layers: the native eraser must not erase the
        # displayed old strokes. Original layer locks are never changed.
        for layer in temporary.layers:
            layer.lock = True
        layer = temporary.layers.new("Codex draw " + token[:8], set_active=True)
        layer.lock = False
        setattr(scene, attribute, temporary)
    except Exception:
        if temporary.users == 0:
            collection.remove(temporary)
        raise
    session = SimpleNamespace(token=token, bpy=bpy, scene=scene, attribute=attribute,
                              collection=collection, original=original, temporary=temporary,
                              layer=layer, window=window, area=area, region=region,
                              window_id=_pointer(window), area_id=_pointer(area),
                              previous_tool=previous_tool, manager=context.window_manager,
                              timer=None, context=context)
    _draw = session
    return session


def is_drawing(context):
    _main_thread()
    return _draw is not None and _owner(context, _draw)


def _dispose(session, context, restore_tool=True):
    errors = []
    if session.timer is not None:
        try:
            session.manager.event_timer_remove(session.timer)
        except (ReferenceError, RuntimeError):
            pass
        session.timer = None
    try:
        if getattr(session.scene, session.attribute) == session.temporary:
            setattr(session.scene, session.attribute, session.original)
        # A user may deliberately link the temporary data into another scene.
        # Never unlink/delete shared data on their behalf.
        if session.temporary.users == 0:
            session.collection.remove(session.temporary)
    except ReferenceError:
        pass  # File load/window destruction already removed the owned IDs.
    if restore_tool:
        try:
            with context.temp_override(window=session.window, area=session.area, region=session.region):
                result = session.bpy.ops.wm.tool_set_by_id(name=session.previous_tool, space_type="VIEW_3D")
            if "FINISHED" not in result:
                errors.append("Previous viewport tool could not be restored")
        except (ReferenceError, RuntimeError, TypeError) as exc:
            errors.append("Previous viewport tool could not be restored: " + str(exc))
    try:
        session.area.tag_redraw()
    except ReferenceError:
        pass
    if errors:
        raise RuntimeError("; ".join(errors))


def cancel_draw(context=None):
    """Discard the current operation, restoring prior annotations/tool.

    A supplied context must own the drawing viewport. None is for main-thread
    load_pre/unregister cleanup, including when no editor context is available.
    Returns False if no matching operation was active. Does not hide any UI.
    """
    global _draw
    _main_thread()
    if _draw is None or (context is not None and not _owner(context, _draw)):
        return False
    session, _draw = _draw, None
    _dispose(session, context or session.context)
    return True


def activate(context, bpy, window, area, region):
    global _draw
    _main_thread()
    register(bpy)
    if _draw is not None:
        if _owner(context, _draw):
            return  # Repeated draw clicks remain the same cancellable operation.
        cancel_draw(None)
    with context.temp_override(window=window, area=area, region=region):
        workspace = window.workspace
        tool = workspace.tools.from_space_view3d_mode(context.mode, create=False)
        previous_tool = tool.idname if tool is not None else "builtin.select_box"
        session = _begin(context, bpy, window, area, region, previous_tool)
        try:
            result = bpy.ops.wm.tool_set_by_id(name="builtin.annotate", space_type="VIEW_3D")
            if "FINISHED" not in result:
                raise RuntimeError("Blender could not activate the native Annotate tool")
            result = bpy.ops.codex_markup.escape_guard("INVOKE_DEFAULT", session_token=session.token)
            if "RUNNING_MODAL" not in result:
                raise RuntimeError("Blender could not start scoped markup Escape handling")
        except Exception:
            _draw = None
            _dispose(session, context)
            raise
    area.tag_redraw()


def register(bpy=None):
    """Register one operator, no global keymap or global Escape binding."""
    global _operator_class
    _main_thread()
    if _operator_class is not None:
        return
    bpy = bpy or importlib.import_module("bpy")

    class CODEX_MARKUP_OT_escape_guard(bpy.types.Operator):
        bl_idname = "codex_markup.escape_guard"
        bl_label = "Codex drawing operation"
        bl_options = {"INTERNAL"}
        session_token: bpy.props.StringProperty(options={"SKIP_SAVE"})

        def invoke(self, context, _event):
            if _draw is None or self.session_token != _draw.token or not _owner(context, _draw):
                return {"CANCELLED"}
            _draw.timer = context.window_manager.event_timer_add(.2, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}

        def modal(self, context, event):
            session = _draw
            if session is None or session.token != self.session_token:
                return {"FINISHED"}
            try:
                exists = any(_pointer(area) == session.area_id and area.type == "VIEW_3D"
                             for area in session.window.screen.areas)
            except ReferenceError:
                exists = False
            if not exists:
                cancel_draw(None)
                return {"FINISHED"}
            if (event.type == "ESC" and event.value == "PRESS" and _owner(context, session)):
                cancel_draw(context)
                return {"FINISHED"}
            return {"PASS_THROUGH"}

        def cancel(self, _context):
            if _draw is not None and _draw.token == self.session_token:
                cancel_draw(None)

    bpy.utils.register_class(CODEX_MARKUP_OT_escape_guard)
    _operator_class = CODEX_MARKUP_OT_escape_guard


def unregister():
    global _operator_class
    _main_thread()
    try:
        cancel_draw(None)
    finally:
        if _operator_class is not None:
            bpy = importlib.import_module("bpy")
            bpy.utils.unregister_class(_operator_class)
            _operator_class = None
