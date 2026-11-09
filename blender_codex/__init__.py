"""Blender integration for the embedded Codex web chat."""

bl_info = {
    "name": "Codex Chat",
    "author": "Blender Codex contributors",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Codex",
    "description": "Chat with Codex using the existing local Blender MCP integration",
    "category": "3D View",
}

import json
import os
from pathlib import Path
import queue
import textwrap

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, PointerProperty, StringProperty
from .official_backend import DEFAULT_MCP_COMMAND, DEFAULT_MCP_ARGS
from .session_state import SessionState


class _Session(SessionState):
    """Ephemeral state: never attach transcript or transport to a scene."""

    def __init__(self):
        super().__init__()


_session = _Session()
_registered = False
_registered_classes = []


def _ensure_history():
    if _session.history_store is None:
        from .chat_history import ChatHistory
        directory = os.environ.get("BLENDER_CODEX_HISTORY_DIR") or bpy.utils.user_resource("DATAFILES", path="blender_codex/history", create=True)
        if not directory:
            raise ValueError("The plugin history directory is unavailable.")
        _session.history_store = ChatHistory(directory)
    return _session.history_store


def _persist_history():
    history = _session.history_store
    if history is None or not history.owned(_session.thread_id):
        return
    try:
        if history.title(_session.thread_id) == "New chat":
            first = next((m.get("text", "") for m in _session.messages if m.get("role") == "You" and not m.get("pending")), "")
            if first.strip():
                history.rename(_session.thread_id, first.strip().splitlines()[0][:80])
        history.save(_session.thread_id, _session.history_projection(), _session.resources.export())
        _session.history_error = ""
    except Exception as exc:
        _session.history_error = "Chat history could not be saved: " + str(exc)


def _open_history_thread(context, thread_id):
    if _session.busy or (_session.client is not None and not _session.ready):
        raise ValueError("Stop or finish the active turn/connection before switching chats.")
    history = _ensure_history()
    history.require(thread_id)  # Ownership before disconnecting the current chat.
    if thread_id == _session.thread_id and _session.ready:
        return
    projection, resources, missing = history.load(thread_id)
    _disconnect()
    _session.restore_projection(projection, resources, missing)
    _session.thread_id = _session.resume_thread_id = thread_id
    _session.history_loading = True
    if bpy.ops.codex_chat.connect() != {"FINISHED"}:
        _session.history_loading = False
        raise ValueError(_session.error or "The selected chat could not be resumed.")


def _redraw():
    for manager in bpy.data.window_managers:
        for window in manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()


def _disconnect(status="Disconnected", clear_history=False):
    # Manual disconnect invalidates worker callbacks, so finalize pending UI
    # items here too rather than leaving cards permanently marked running.
    _session.apply({"type": "closed"})
    _persist_history()
    # Invalidate callbacks before close: a worker may still emit a final event.
    _session.generation += 1
    client, _session.client = _session.client, None
    _session.ready = False
    _session.history_loading = False
    _session.busy = False
    _session.stream = None
    _session.approvals.clear()
    _session.activity = ""
    _session.status = status
    _session.error = ""
    if clear_history:
        _session.reset_history()
    if client is not None:
        try:
            client.close()
        except Exception as exc:
            _session.error = "Could not close Codex: {}".format(exc)


def _handle_event(event):
    _session.apply(event)
    kind = event.get("type")
    text = str(event.get("text", ""))
    if kind == "status":
        _session.status = text
    elif kind == "ready":
        _session.ready = True
        _session.status = "Connected"
        _session.history_loading = False
        try:
            history = _ensure_history()
            if event.get("resumed"):
                history.require(_session.thread_id)
                title = history.title(_session.thread_id)
                if title != "New chat":
                    _session.client.rename(title)
            else:
                history.register(_session.thread_id, _session.project_root or "")
            _persist_history()
        except Exception as exc:
            _session.history_error = str(exc)
    elif kind in ("delta", "message", "message_final", "approval", "approval_resolved", "user_item"):
        return
    elif kind == "activity":
        _session.activity = text
    elif kind == "error":
        _session.error = text or "Unknown Codex error"
        # The transport may reject a turn without emitting done afterwards.
        if event.get("fatal") or event.get("rejected"):
            _session.busy = False
            _session.stream = None
        _session.status = "Error"
        if _session.history_loading:
            _session.history_error = text
    elif kind == "done":
        _session.busy = False
        _session.stream = None
        _session.approvals.clear()
        _session.status = "Connected" if _session.ready else "Disconnected"
        _persist_history()
    elif kind == "thread_renamed":
        try:
            _ensure_history().rename(event["thread_id"], event["title"])
        except Exception as exc:
            _session.history_error = str(exc)
    elif kind == "closed":
        error = _session.error
        _disconnect()
        if error:
            _session.error = error
            _session.status = "Disconnected — error"


def _drain_events():
    if not _registered:
        return None
    changed = False
    # Bound work per tick so long streams do not starve Blender's UI.
    for _ in range(200):
        try:
            generation, event = _session.events.get_nowait()
        except queue.Empty:
            break
        if generation == _session.generation:
            _handle_event(event)
            changed = True
    if changed:
        _redraw()
    return 0.1


@persistent
def _on_load_pre(_dummy):
    from . import annotations
    annotation_error = None
    try:
        annotations.cancel_draw(None)
    except Exception as exc:
        annotation_error = str(exc)
    from . import web_ui
    web_ui.reset_for_file_load()
    _session.status = "File changed — active turn remains bound to its original scene"
    if annotation_error:
        _session.error = annotation_error
    for manager in bpy.data.window_managers:
        if hasattr(manager, "codex_chat"):
            manager.codex_chat.input_text = ""
            manager.codex_chat.include_view = False


def _preferences(context):
    addon = context.preferences.addons.get(__package__)
    if addon is None:
        raise RuntimeError("Codex Chat add-on preferences are unavailable")
    return addon.preferences


def _wrapped(layout, text, width, icon=None):
    # label() does not wrap and interprets embedded newlines inconsistently.
    first = True
    for paragraph in str(text).expandtabs(4).split("\n"):
        for line in textwrap.wrap(paragraph, width=width, replace_whitespace=False) or [""]:
            if first and icon:
                layout.label(text=line, icon=icon)
            else:
                layout.label(text=line)
            first = False


class CODEX_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    codex_path: StringProperty(
        name="Codex executable", default="codex",
        description="Executable name on PATH or absolute path to Codex",
    )
    mcp_command: StringProperty(
        name="MCP executable", default=DEFAULT_MCP_COMMAND,
        description="Prepared official Blender Lab MCP Python executable; empty uses Codex configuration",
    )
    mcp_args: StringProperty(
        name="MCP arguments (JSON)", default=json.dumps(list(DEFAULT_MCP_ARGS)),
        description="JSON array of strings passed to the MCP executable",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "codex_path")
        layout.prop(self, "mcp_command")
        layout.prop(self, "mcp_args")
        layout.label(text="Uses your existing Codex login.")
        layout.label(text="Uses the prepared official Blender Lab MCP.")


class CODEX_ChatState(bpy.types.PropertyGroup):
    input_text: StringProperty(name="Message", options={"SKIP_SAVE"})
    include_view: BoolProperty(
        name="Ansicht mitsenden (inkl. Sidebar)", default=False, options={"SKIP_SAVE"},
        description="Send a screenshot of this 3D editor, including annotations and sidebar",
    )


class CODEX_OT_draw(bpy.types.Operator):
    bl_idname = "codex_chat.draw"
    bl_label = "Zeichnen"
    bl_description = "Activate Blender's annotation tool in the current 3D editor"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        try:
            from .annotations import activate_draw
            result = activate_draw(context)
            if result == {"CANCELLED"}:
                raise RuntimeError("Annotation tool could not be activated")
        except Exception as exc:
            _session.error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class CODEX_OT_connect(bpy.types.Operator):
    bl_idname = "codex_chat.connect"
    bl_label = "Connect"
    bl_description = "Start a local Codex connection for the current project"

    @classmethod
    def poll(cls, context):
        return _session.client is None

    def execute(self, context):
        try:
            from .codex_client import CodexClient
            from .native_tools import NativeTools
            from .context import project_directory
            from .blender_target import target_environment

            prefs = _preferences(context)
            mcp_target = target_environment(context.preferences.addons)
            history = _ensure_history()
            resume_id = _session.resume_thread_id
            if resume_id is None and history.owned(_session.thread_id):
                resume_id = _session.thread_id
                projection, resources, missing = history.load(resume_id)
                _session.restore_projection(projection, resources, missing)
                _session.thread_id = resume_id
            if resume_id is not None:
                history.require(resume_id)
            args = json.loads(prefs.mcp_args)
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise ValueError("MCP arguments must be a JSON array of strings")
            if not prefs.codex_path.strip():
                raise ValueError("Set the Codex executable in add-on preferences")
            _session.generation += 1
            generation = _session.generation
            events = _session.events

            def callback(event):
                # This callback runs on workers. No Blender API access here.
                events.put((generation, dict(event)))

            _session.error = ""
            _session.activity = ""
            # A new transport starts a new Codex thread, so start a fresh chat.
            # Reconnect starts a fresh authoritative thread; preserve explicit
            # composer attachments until sent/removed, rather than losing uploads.
            if resume_id is None:
                _session.messages.clear()
                _session.tool_calls.clear()
                _session.artifacts.clear()
                _session._messages.clear()
                _session._tools.clear()
                _session.thread_id = None
            _session.history_loading = resume_id is not None
            _session.project_root = project_directory()
            _session.stream = None
            _session.status = "Connecting…"
            provider = context.window_manager.hi3d_settings
            credentials = (provider.client_id, provider.client_secret)
            native = NativeTools(
                Path(bpy.utils.user_resource("DATAFILES", path="blender_codex", create=True)) / "hi3d_tools",
                credentials=credentials if any(credentials) else None, cwd=project_directory(),
                env_file=bpy.path.abspath(provider.env_file) if provider.env_file else None)
            _session.client = CodexClient(callback, native_tools=native)
            _session.client.start(
                codex_path=prefs.codex_path.strip(), cwd=project_directory(),
                mcp_command=prefs.mcp_command.strip(), mcp_args=args,
                permission_mode=_session.permission_mode,
                model=_session.selected_model, reasoning_effort=_session.reasoning_effort,
                mcp_env=mcp_target,
                resume_thread_id=resume_id,
            )
        except Exception as exc:
            _disconnect()
            _session.error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        _redraw()
        return {"FINISHED"}


class CODEX_OT_disconnect(bpy.types.Operator):
    bl_idname = "codex_chat.disconnect"
    bl_label = "Disconnect"

    @classmethod
    def poll(cls, context):
        return _session.client is not None

    def execute(self, context):
        _disconnect()
        _redraw()
        return {"FINISHED"}


class CODEX_OT_new_chat(bpy.types.Operator):
    bl_idname = "codex_chat.new_chat"
    bl_label = "New chat"
    bl_description = "Clear this conversation and reconnect to start a new Codex thread"

    @classmethod
    def poll(cls, context):
        return _session.client is not None and not _session.busy

    def execute(self, context):
        _disconnect(clear_history=True)
        return bpy.ops.codex_chat.connect()


class CODEX_OT_send(bpy.types.Operator):
    bl_idname = "codex_chat.send"
    bl_label = "Send"
    bl_description = "Send this message with freshly collected scene context"

    @classmethod
    def poll(cls, context):
        return (_session.client is not None and _session.ready and not _session.busy
                and bool(context.window_manager.codex_chat.input_text.strip()))

    def execute(self, context):
        text = context.window_manager.codex_chat.input_text.strip()
        try:
            _send_message(context, text, bool(context.window_manager.codex_chat.include_view))
        except Exception as exc:
            _session.error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        context.window_manager.codex_chat.input_text = ""
        _redraw()
        return {"FINISHED"}


def _send_message(context, text, include_view=False, attachment_ids=None):
    """Main-thread-only preparation; HTTP callers provide capability handles."""
    from .context import collect_context, project_directory
    from . import scene_lifecycle
    if not _session.ready or _session.busy or _session.client is None:
        raise ValueError("Codex is not ready for a new turn.")
    with _session.client._lock:
        if not _session.client._ready or _session.client._busy or _session.client._closing:
            raise ValueError("Codex is not ready for a new turn.")
    if project_directory() != _session.project_root:
        raise ValueError("Project directory changed; reconnect Codex before sending to this scene.")
    images, texts, handles = _session.attachment_inputs(attachment_ids)
    scene_context = collect_context(context)
    if include_view:
        from .annotations import capture_view, view_metadata
        from pathlib import Path
        path = capture_view(context)
        descriptor = _session.resources.add("viewport.png", "image/png", Path(path).read_bytes())
        # Send the immutable registered copy, so UI and model see the same bytes.
        images.append(str(_session.resources.get(descriptor["id"])[1]))
        _session.artifacts.append(descriptor)
        handles.append(descriptor["id"])
        scene_context["view"] = view_metadata(context)
        scene_context["image_note"] = "Screenshot with annotations: visual guidance, not exact mesh selection."
    scene_context.update(scene_lifecycle.bind_turn(context, context.preferences.addons))
    if _session.client.send(text, scene_context, image_paths=images or None, attachment_texts=texts or None) is not True:
        raise ValueError("Codex did not accept this submission. Check connection and attachments.")
    _session.pending_user(text, handles, include_view)
    _session.attachments[:] = [a for a in _session.attachments if a["id"] not in handles]
    _session.busy, _session.stream = True, None
    _session.error, _session.activity, _session.status = "", "", "Working…"


class CODEX_OT_stop(bpy.types.Operator):
    bl_idname = "codex_chat.stop"
    bl_label = "Stop"
    bl_description = "Request interruption of the active Codex turn"

    @classmethod
    def poll(cls, context):
        return _session.client is not None and _session.busy

    def execute(self, context):
        try:
            _session.client.interrupt()
            _session.status = "Stopping…"
        except Exception as exc:
            _session.error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        _redraw()
        return {"FINISHED"}


class CODEX_OT_approve(bpy.types.Operator):
    bl_idname = "codex_chat.approve"
    bl_label = "Respond to approval"
    bl_description = "Allow Codex to perform the described action, or deny this request"
    approved: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return _session.client is not None and bool(_session.approvals)

    def execute(self, context):
        request = _session.approvals[0]
        try:
            _session.client.approve(request["request_id"], self.approved)
        except Exception as exc:
            _session.error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        _session.approvals.pop(0)
        _redraw()
        return {"FINISHED"}


class CODEX_OT_open_web(bpy.types.Operator):
    bl_idname = "codex_chat.open_web"
    bl_label = "Chat wieder anzeigen"
    bl_description = "Restore the minimized embedded chat in this sidebar"

    def execute(self, context):
        try:
            from . import web_ui
            web_ui.open_panel(context)
        except Exception as exc:
            _session.error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class CODEX_PT_chat(bpy.types.Panel):
    bl_label = "Codex"
    bl_idname = "CODEX_PT_chat"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Codex"
    bl_options = {"HIDE_HEADER"}

    def draw(self, context):
        layout = self.layout
        from . import web_ui
        status = web_ui.panel_status(context)
        if status == "minimized":
            layout.label(text="Chat minimiert")
            layout.operator("codex_chat.open_web", icon="WINDOW")
        elif status == "error":
            layout.operator("codex_chat.open_web", text="Erneut versuchen", icon="FILE_REFRESH")
            width = max(16, int(context.region.width / 7) - 5)
            _wrapped(layout, _session.error or "Chat konnte nicht geöffnet werden.", width, "ERROR")
        else:
            layout.label(text="Chat wird geöffnet…")


_CLASSES = (
    CODEX_Preferences, CODEX_ChatState, CODEX_OT_draw, CODEX_OT_connect, CODEX_OT_disconnect,
    CODEX_OT_new_chat,
    CODEX_OT_send, CODEX_OT_stop, CODEX_OT_approve, CODEX_OT_open_web, CODEX_PT_chat,
)


def register():
    global _registered
    from . import hi3d_ui
    if _registered:
        return
    try:
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
            _registered_classes.append(cls)
        bpy.types.WindowManager.codex_chat = PointerProperty(type=CODEX_ChatState)
        bpy.app.handlers.load_pre.append(_on_load_pre)
        _registered = True
        bpy.app.timers.register(_drain_events, first_interval=0.1, persistent=True)
        hi3d_ui.register()
        from . import annotations
        annotations.register()
        from . import scene_lifecycle
        scene_lifecycle.register()
        from . import web_ui
        web_ui.register()
    except Exception:
        unregister()
        raise


def unregister():
    global _registered
    from . import annotations
    annotation_error = None
    try:
        annotations.unregister()
    except Exception as exc:
        annotation_error = str(exc)
    from . import web_ui
    web_ui.unregister()
    from . import hi3d_ui
    hi3d_ui.unregister()
    _registered = False
    _disconnect(clear_history=True)
    from . import scene_lifecycle
    scene_lifecycle.unregister()
    if bpy.app.timers.is_registered(_drain_events):
        bpy.app.timers.unregister(_drain_events)
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    if hasattr(bpy.types.WindowManager, "codex_chat"):
        del bpy.types.WindowManager.codex_chat
    while _registered_classes:
        bpy.utils.unregister_class(_registered_classes.pop())
    if annotation_error:
        raise RuntimeError(annotation_error)
