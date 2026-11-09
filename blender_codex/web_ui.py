"""Main-thread adapter between the web chat, Blender operators and native host."""

import queue
import sys

import bpy

_bridge = None
_host = None
_image_host = None
_image_editor_id = None
_image_failed_id = None
_panel_url = None
_window_pointer = None
_area_pointer = None
_visible = False
_registered = False
_active_tabs = set()
_suppressed = set()
_failed = set()
_startup_pending = False
_minimized_by_user = False
_suppress_initial_tabs = False
_startup_attempts = 0
_preferred_chat_width = None
_manual_layout = None
_layout_loaded = False
_auto = None


def _layout_path():
    from pathlib import Path
    return Path(bpy.utils.user_resource("DATAFILES", path="blender_codex", create=True)) / "chat-layout-v1.json"


def _request_connection():
    global _auto
    from .auto_connect import AutoConnect
    if _auto is None:
        _auto = AutoConnect()
    else:
        _auto.request()


def _autoconnect_tick():
    if not _registered:
        return None
    if bpy.app.background:
        return 1.0
    from . import _session
    if _auto is None:
        _request_connection()
    try:
        _auto.tick(_session, lambda: bpy.ops.codex_chat.connect())
    except Exception as exc:
        _session.error = str(exc)
    return 1.0


def _close_legacy_markup():
    """Retire a pre-upgrade toolbar host without reserving a second surface."""
    legacy = globals().pop("_markup_host", None)
    if legacy is not None:
        try:
            legacy.close()
        except Exception:
            pass


def _window_is_minimized():
    """Read the native parent's iconic state, without touching agent lifetime."""
    if _host is None or sys.platform != "win32":
        return False
    parent = getattr(_host, "parent_hwnd", None)
    if not parent:
        return False
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    return bool(user32.IsIconic(parent))


def _hide_surfaces():
    for host in (_host, _image_host):
        if host is not None:
            host.hide()


def _key(context):
    return context.window.as_pointer(), context.area.as_pointer()


def panel_status(context):
    """Read-only draw helper; never launch subprocesses from Panel.draw()."""
    key = _key(context)
    if key in _suppressed:
        return "minimized"
    if key in _failed:
        return "error"
    return "opening"


def _watch_tabs():
    try:
        return _watch_tabs_impl()
    except Exception as exc:
        # A workspace may disappear or be rebuilt between UI frames. A timer
        # exception must never permanently remove the startup/tab watcher.
        from . import _session
        _session.error = "Webchat konnte nicht angezeigt werden: {}".format(exc)
        _failed.update(_active_tabs)
        close()
        return 0.5 if _registered else None


def _watch_tabs_impl():
    """Wait for startup regions, then watch explicit Codex-tab transitions."""
    global _active_tabs, _startup_pending, _suppress_initial_tabs, _startup_attempts
    if not _registered:
        return None
    if bpy.app.background:
        return 0.1
    if _window_is_minimized():
        return 0.2
    if _startup_pending:
        viewports = [(window, area) for manager in bpy.data.window_managers
                     for window in manager.windows for area in window.screen.areas
                     if area.type == "VIEW_3D" and window.width > 100 and window.height > 100]
        if not viewports:
            return 0.1
        active_window = getattr(bpy.context, "window", None)
        window, area = max(viewports, key=lambda pair: (
            pair[0] == active_window, getattr(pair[1], "width", 1) * getattr(pair[1], "height", 1)))
        area.spaces.active.show_region_ui = True
        area.tag_redraw()
        sidebar = next((r for r in area.regions if r.type == "UI"), None)
        if sidebar is None or sidebar.width <= 40:
            return 0.1
        try:
            # Newly constructed regions can report this dynamic RNA property
            # as read-only until their categories have been drawn once.
            if sidebar.active_panel_category != "Codex":
                sidebar.active_panel_category = "Codex"
        except (AttributeError, TypeError, RuntimeError):
            _startup_attempts += 1
            if _startup_attempts >= 150:
                from . import _session
                _session.error = "Codex-Tab noch nicht verfügbar. Bitte den Codex-Tab wählen oder den Chat erneut anzeigen."
                _failed.add((window.as_pointer(), area.as_pointer()))
                _startup_pending = False
            return 0.2
        _startup_attempts = 0
        _startup_pending = False
    candidates = []
    layout_ready = False
    for manager in bpy.data.window_managers:
        for window in manager.windows:
            for area in window.screen.areas:
                if area.type != "VIEW_3D" or not area.spaces.active.show_region_ui:
                    continue
                sidebar = next((r for r in area.regions if r.type == "UI"), None)
                if sidebar is not None and sidebar.width > 40:
                    layout_ready = True
                if sidebar is not None and sidebar.width > 40 and sidebar.active_panel_category == "Codex":
                    candidates.append(((window.as_pointer(), area.as_pointer()), window, area))
    current = {key for key, _window, _area in candidates}
    if _suppress_initial_tabs and current:
        _suppressed.update(current)
        _suppress_initial_tabs = False
    elif _suppress_initial_tabs and layout_ready:
        _suppress_initial_tabs = False
    exited = _active_tabs - current
    _suppressed.difference_update(exited)
    _failed.difference_update(exited)
    entered = current - _active_tabs
    _active_tabs = current
    for key, window, area in candidates:
        if key not in entered or key in _suppressed or key in _failed:
            continue
        try:
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            with bpy.context.temp_override(window=window, area=area, region=region):
                open_panel(bpy.context)
        except Exception as exc:
            from . import _session
            _session.error = str(exc)
            _failed.add(key)
            area.tag_redraw()
        # Only one host is supported; never cycle between multiple active areas.
        break
    return 0.1


def _owner():
    for manager in bpy.data.window_managers:
        for window in manager.windows:
            if window.as_pointer() != _window_pointer:
                continue
            for area in window.screen.areas:
                if area.as_pointer() == _area_pointer and area.type == "VIEW_3D":
                    return window, area
    return None, None


def _snapshot(context):
    from . import _session, _preferences, _ensure_history
    from .official_backend import resolve_launch, OfficialBackendError
    prefs = _preferences(context)
    try:
        _ensure_history()
    except Exception as exc:
        _session.history_error = str(exc)
    backend_ready = True
    try:
        resolve_launch(prefs.mcp_command.strip())
    except OfficialBackendError:
        backend_ready = False
    # A lightweight live context for display. The full scene/mesh context is
    # collected separately by the send operator at the moment of submission.
    active = context.active_object
    from . import annotations
    return {
        **_session.snapshot_fields(),
        "backend_ready": backend_ready,
        "ready": _session.ready, "busy": _session.busy,
        "status": _session.status, "error": _session.error,
        "activity": _session.activity,
        "markup_active": annotations.is_drawing(context),
        "messages": [dict(item) for item in _session.messages],
        "approvals": [dict(item) for item in _session.approvals],
        "context": {
            "filepath": bpy.data.filepath or "", "is_unsaved": not bpy.data.filepath,
            "active_object": {"name": active.name} if active else None,
            "selected_objects": [{"name": obj.name} for obj in context.selected_objects],
        },
        "settings": {"codex_path": prefs.codex_path,
                     "mcp_command": prefs.mcp_command, "mcp_args": prefs.mcp_args},
    }


def _action(command, context):
    global _visible, _minimized_by_user, _startup_pending
    from . import _session, _preferences
    import json

    action = command.get("action")
    if action == "markup_cancel":
        from . import annotations
        canceled = annotations.cancel_draw(context)
        return {"ok": True, "canceled": canceled}
    if action == "threads/list":
        from . import _ensure_history
        return {"ok": True, "threads": _ensure_history().threads()}
    if action == "threads/open":
        from . import _open_history_thread
        _open_history_thread(context, command["thread_id"])
        return {"ok": True, "pending": not _session.ready}
    if action == "threads/new":
        if _session.busy or (_session.client is not None and not _session.ready):
            raise ValueError("Wait for the active turn/connection before starting another chat.")
        from . import _disconnect
        _disconnect(clear_history=True)
        if bpy.ops.codex_chat.connect() != {"FINISHED"}:
            raise ValueError(_session.error or "Could not start a new chat.")
        return {"ok": True, "pending": True}
    if action == "threads/rename":
        from . import _ensure_history
        if _session.busy:
            raise ValueError("Wait for the active turn before renaming a chat.")
        _ensure_history().rename(command["thread_id"], command["title"])
        active = _session.thread_id == command["thread_id"] and _session.ready and _session.client is not None
        if active:
            _session.client.rename(command["title"])
        return {"ok": True, "server_pending": active, "scope": "server-and-plugin" if active else "plugin-index"}
    if action in ("select_model", "select_effort", "set_permission", "set_permission_mode"):
        if _session.busy:
            raise ValueError("Wait for this turn before changing its configuration.")
        if action.startswith("set_permission") and _session.client is None:
            mode = command["permission_mode"]
            if mode not in ("full_access", "on_request", "read_only"):
                raise ValueError("Unknown permission mode.")
            _session.permission_mode = mode
        else:
            if _session.client is None or not _session.ready:
                raise ValueError("Connect to load the actual Codex model catalog first.")
            values = ({"permission_mode": command["permission_mode"]} if action.startswith("set_permission") else
                      {"reasoning_effort": command["reasoning_effort"]} if action == "select_effort" else
                      {"model": command.get("model_id", command.get("model")), "reasoning_effort": command.get("reasoning_effort")})
            _session.client.configure(**values)
            _session.selected_model = _session.client.selected_model
            _session.reasoning_effort = _session.client.reasoning_effort
            _session.permission_mode = _session.client.permission_mode
        return {"ok": True}
    if action in ("attach_file", "upload_attachment"):
        descriptor = _session.resources.upload(command["name"], command.get("mime_type", command.get("mime", "")), command["data_base64"])
        _session.attachments.append(descriptor)
        return {"ok": True, "attachment": descriptor, "resource": descriptor}
    if action == "remove_attachment":
        handle = command["resource_id"]
        if not any(a["id"] == handle for a in _session.attachments):
            raise ValueError("Attachment no longer exists in this composer.")
        _session.attachments[:] = [a for a in _session.attachments if a["id"] != handle]
        return {"ok": True}
    if action == "settings":
        if _session.busy or bool(getattr(_session.client, "_busy", False)) or (_session.client is not None and not _session.ready):
            raise ValueError("Bitte den laufenden Auftrag oder Verbindungsaufbau abwarten.")
        prefs = _preferences(context)
        values = {key: command.get(key, getattr(prefs, key))
                  for key in ("codex_path", "mcp_command", "mcp_args")}
        if isinstance(values["mcp_args"], list):
            values["mcp_args"] = json.dumps(values["mcp_args"])
        if not all(isinstance(value, str) and len(value) <= 8192 for value in values.values()):
            raise ValueError("Ungültige Verbindungseinstellungen.")
        if not values["codex_path"].strip():
            raise ValueError("Der Codex-Pfad darf nicht leer sein.")
        args = json.loads(values["mcp_args"])
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ValueError("MCP-Argumente müssen ein JSON-Array aus Zeichenketten sein.")
        for key, value in values.items():
            setattr(prefs, key, value)
        if _session.client is not None:
            from . import _disconnect
            _disconnect(status="Reconnecting…")
        _session.error = ""
        _request_connection()
        return {"ok": True}
    if action == "hide_panel":
        _visible = False
        _minimized_by_user = True
        _startup_pending = False
        _suppressed.add(_key(context))
        if _host:
            _host.hide()
        if _image_host:
            _image_host.hide()
        context.area.tag_redraw()
        return {"ok": True}
    if action == "provider_settings":
        _visible = False
        _minimized_by_user = True
        _suppressed.add(_key(context))
        sidebar = next((r for r in context.area.regions if r.type == "UI"), None)
        if sidebar is not None:
            sidebar.active_panel_category = "3D Providers"
        if _host:
            _host.hide()
        if _image_host:
            _image_host.hide()
        context.area.tag_redraw()
        return {"ok": True}
    if action == "send":
        text = command.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 100000:
            raise ValueError("Bitte eine Nachricht mit höchstens 100.000 Zeichen eingeben.")
        include = command.get("include_view", False)
        if not isinstance(include, bool):
            raise ValueError("Ungültige Ansichtsauswahl.")
        if not _session.ready or _session.busy:
            raise ValueError("Codex ist noch nicht bereit für eine neue Nachricht.")
        from . import _send_message
        _send_message(context, text, include, command.get("attachment_ids"))
        return {"ok": True}
    if action in ("approve", "respond"):
        # Check the ID, not just the first pending item, to avoid acting on a
        # different request when the browser displays a stale snapshot.
        request_id = command.get("request_id")
        if not isinstance(command.get("approved"), bool):
            raise ValueError("Ungültige Freigabe.")
        pending = next((item for item in _session.approvals
                        if item["request_id"] == request_id), None)
        if pending is None or _session.client is None:
            raise ValueError("Diese Freigabe ist nicht mehr offen.")
        _session.client.respond(request_id, command["approved"], command.get("values"), command.get("answers"))
        return {"ok": True}
    operators = {
        "connect": bpy.ops.codex_chat.connect,
        "disconnect": bpy.ops.codex_chat.disconnect,
        "new_chat": bpy.ops.codex_chat.new_chat,
        "send": bpy.ops.codex_chat.send,
        "stop": bpy.ops.codex_chat.stop,
        "draw": bpy.ops.codex_chat.draw,
    }
    operator = operators.get(action)
    if operator is None:
        raise ValueError("Unbekannte Chat-Aktion.")
    if not operator.poll():
        raise ValueError("Diese Aktion ist im aktuellen Zustand nicht verfügbar.")
    if operator() != {"FINISHED"}:
        raise RuntimeError(_session.error or "Die Aktion konnte nicht ausgeführt werden.")
    return {"ok": True}


def _tick():
    try:
        return _tick_impl()
    except Exception as exc:
        from . import _session
        _session.error = "Webchat-Verbindung zur Oberfläche unterbrochen: {}".format(exc)
        _failed.add((_window_pointer, _area_pointer))
        close()
        return None


def _tick_impl():
    global _preferred_chat_width
    global _image_host, _image_editor_id, _image_failed_id
    global _manual_layout
    from . import _session
    if _bridge is None:
        return None
    _close_legacy_markup()
    if _window_is_minimized():
        # Codex's subprocess/event workers and the independent session event
        # drain keep running. Do not destroy/reconnect the chat for OS minimize.
        _hide_surfaces()
        return 0.2
    window, area = _owner()
    if window is None:
        reset_for_file_load()
        return None
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    with bpy.context.temp_override(window=window, area=area, region=region):
        for _ in range(20):
            try:
                command, response = _bridge.commands.get_nowait()
            except queue.Empty:
                break
            try:
                result = _action(command, bpy.context)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            response.put(result)
        _bridge.resources = _session.resources
        _bridge.publish(_snapshot(bpy.context))
    sidebar = next((r for r in area.regions if r.type == "UI"), None)
    show = (_visible and sidebar is not None and sidebar.width > 40
            and area.spaces.active.show_region_ui
            and sidebar.active_panel_category == "Codex")
    image_markup = getattr(_session, "image_markup", None)
    editor_id = image_markup.get("id") if isinstance(image_markup, dict) else None
    if _image_host is not None and editor_id != _image_editor_id:
        _image_host.close()
        _image_host = None
        _image_editor_id = None
    if editor_id and show and _image_host is None and editor_id != _image_failed_id:
        try:
            from .web_host import WebHost
            _image_host = WebHost(_panel_url + "&surface=image-editor")
            _image_host.start()
            _image_editor_id = editor_id
        except Exception as exc:
            if _image_host is not None:
                _image_host.close()
            _image_host = None
            _image_failed_id = editor_id
            _session.error = "Die Bildansicht konnte nicht geöffnet werden: {}".format(exc)
    editor_visible = bool(editor_id and _image_host is not None and show)
    chat_left = sidebar.x if sidebar is not None else area.x + area.width
    if _host is not None:
        if not _host.alive:
            from . import _session
            _session.error = _host.error or "Das Chat-Fenster wurde geschlossen. Bitte erneut öffnen."
            _failed.add((_window_pointer, _area_pointer))
            close()
            area.tag_redraw()
            return None
        if show:
            # Keep Blender's resize edge and category tabs accessible. Region
            # coordinates are bottom-origin, native client pixels top-origin.
            scale = max(bpy.context.preferences.system.ui_scale, 0.5)
            border, tabs = 4, round(26 * scale)
            client_width, client_height = _host.parent_client_size
            sx = client_width / max(window.width, 1)
            sy = client_height / max(window.height, 1)
            from .panel_layout import clamp_bounds, normalize, restore, save
            viewport = (round((area.x + border)*sx), round((window.height-area.y-area.height)*sy),
                        max(1,round((area.width-2*border)*sx)), max(1,round(area.height*sy)))
            changed = getattr(_host, "requested_bounds", None)
            if changed is not None:
                bounds = clamp_bounds(tuple(changed[k] for k in ("x","y","width","height")), viewport)
                _manual_layout = normalize(bounds, viewport)
                _host.requested_bounds = None
                if changed.get("final"):
                    _host._geometry = None  # enforce final viewport clamp after native gesture ends
                    try: save(_layout_path(), _manual_layout)
                    except OSError as exc: _session.error = "Chat layout could not be saved: " + str(exc)
            if _manual_layout is not None:
                bounds = restore(_manual_layout, viewport)
            else:
                bounds = clamp_bounds((round((sidebar.x+border)*sx),
                    round((window.height-sidebar.y-sidebar.height)*sy),
                    round((sidebar.width-border-tabs)*sx), round(sidebar.height*sy)), viewport)
            chat_left = bounds[0]/max(sx,.01)
            _host.update(*bounds)
        else:
            _host.hide()
    if _image_host is not None:
        if not _image_host.alive:
            _session.error = _image_host.error or "Die Bildansicht wurde geschlossen. Bitte das Bild erneut öffnen."
            _image_failed_id = _image_editor_id
            _image_host.close()
            _image_host = None
        elif editor_visible and region is not None:
            scale = max(bpy.context.preferences.system.ui_scale, 0.5)
            client_width, client_height = _image_host.parent_client_size
            sx = client_width / max(window.width, 1)
            sy = client_height / max(window.height, 1)
            inset = max(4, round(8 * scale))
            _image_host.update(round((area.x + inset) * sx),
                               round((window.height - region.y - region.height + inset) * sy),
                               max(1, round((chat_left - area.x - 2 * inset) * sx)),
                               max(1, round((region.height - 2 * inset) * sy)))
        else:
            _image_host.hide()
    return 0.1


def open_panel(context):
    global _bridge, _host, _window_pointer, _area_pointer, _visible
    global _minimized_by_user, _startup_pending
    global _panel_url, _manual_layout, _layout_loaded
    if bpy.app.background:
        raise RuntimeError("Die Web-Oberfläche benötigt ein sichtbares Blender-Fenster.")
    if sys.platform != "win32":
        raise RuntimeError("Die eingebettete Web-Oberfläche unterstützt zunächst Windows.")
    if context.area is None or context.area.type != "VIEW_3D":
        raise RuntimeError("Den Chat bitte in einem 3D-Editor öffnen.")
    _close_legacy_markup()
    if not _layout_loaded:
        from .panel_layout import load
        _manual_layout = load(_layout_path())
        _layout_loaded = True
    _request_connection()
    _suppressed.discard(_key(context))
    _failed.discard(_key(context))
    _minimized_by_user = False
    _startup_pending = False
    if _bridge is not None:
        if _window_pointer == context.window.as_pointer() and _area_pointer == context.area.as_pointer():
            _visible = True
            return
        close()
    from .web_bridge import WebBridge
    from .web_host import WebHost
    _window_pointer = context.window.as_pointer()
    _area_pointer = context.area.as_pointer()
    context.area.spaces.active.show_region_ui = True
    try:
        _bridge = WebBridge()
        from . import _session
        _bridge.resources = _session.resources
        _bridge.publish(_snapshot(context))
        url = _bridge.start()
        _panel_url = url
        _host = WebHost(url)
        _host.start()
        _visible = True
        bpy.app.timers.register(_tick, first_interval=0.1)
    except Exception:
        close()
        _failed.add(_key(context))
        raise


def close():
    """Dispose view resources only; this never closes the Codex session."""
    global _bridge, _host, _window_pointer, _area_pointer, _visible
    global _image_host, _image_editor_id, _image_failed_id, _panel_url
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    host, _host = _host, None
    legacy_markup = globals().pop("_markup_host", None)
    image_host, _image_host = _image_host, None
    _image_editor_id = _image_failed_id = _panel_url = None
    bridge, _bridge = _bridge, None
    _visible = False
    _window_pointer = _area_pointer = None
    for resource, method in ((host, "close"), (legacy_markup, "close"), (image_host, "close"), (bridge, "stop")):
        if resource is not None:
            try:
                getattr(resource, method)()
            except Exception:
                # A crashed helper must not prevent the other host or bridge
                # from being cleaned up, especially during file loading.
                pass


def reset_for_file_load():
    global _startup_pending, _suppress_initial_tabs, _startup_attempts
    close()
    _active_tabs.clear()
    _suppressed.clear()
    _failed.clear()
    _startup_pending = not _minimized_by_user
    _suppress_initial_tabs = _minimized_by_user
    _startup_attempts = 0


def register():
    global _registered, _startup_pending, _minimized_by_user, _startup_attempts
    if _registered:
        return
    _registered = True
    _minimized_by_user = False
    _startup_pending = True
    _startup_attempts = 0
    try:
        bpy.app.timers.register(_watch_tabs, first_interval=0.1, persistent=True)
        _request_connection()
        bpy.app.timers.register(_autoconnect_tick, first_interval=1.0, persistent=True)
    except Exception:
        _registered = False
        raise


def unregister():
    global _registered, _startup_pending, _minimized_by_user, _suppress_initial_tabs
    _registered = False
    if bpy.app.timers.is_registered(_autoconnect_tick):
        bpy.app.timers.unregister(_autoconnect_tick)
    if bpy.app.timers.is_registered(_watch_tabs):
        bpy.app.timers.unregister(_watch_tabs)
    reset_for_file_load()
    _startup_pending = _minimized_by_user = _suppress_initial_tabs = False
