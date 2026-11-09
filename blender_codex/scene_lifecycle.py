"""Keep the agent alive while fencing native MCP execution across file loads.

This is an in-memory guard around the official bridge in THIS Blender process,
not a copied executor or a source patch. It does not stop Codex or clear history.
All lifecycle entry points run on Blender's main thread.
"""
import importlib
import sys
import threading
import uuid

_epoch = uuid.uuid4().hex
_turn_epoch = None
_loading = False
_invalidated = False
_records = []
_handlers = None


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Scene lifecycle changes require Blender's main thread")


def _blocked(expected):
    return _loading or _invalidated or (expected is not None and expected != _epoch)


def _error():
    return {"status": "error", "message": "The Blender file/scene target changed. This turn cannot execute scene code against the new target. Send a new message with fresh scene context.",
            "code": "scene_target_changed"}


def install(addons, modules=None):
    """Wrap enabled official bridge modules; never discover another process."""
    _main_thread()
    modules = sys.modules if modules is None else modules
    for name, _addon in addons.items():
        if name != "blender_mcp_addon" and not name.endswith(".mcp"):
            continue
        server = getattr(modules.get(name), "mcp_to_blender_server", None)
        if server is None:
            continue
        record = next((item for item in _records if item["server"] is server), None)
        if record is not None:
            if server._execute_code is not record["wrapper"]:
                raise RuntimeError("The official scene guard was replaced; refusing an unguarded target")
            continue
        if not all(hasattr(server, key) for key in ("_execute_code", "_ExecResult", "_state", "start", "stop", "is_running")):
            raise RuntimeError("Unsupported official Blender bridge; scene lifecycle guard cannot be installed")
        original = server._execute_code

        def execute(code, strict_json, _server=server, _original=original):
            expected = _turn_epoch
            if _blocked(expected):
                return _server._ExecResult(_error())
            result = _original(code, strict_json)
            check = getattr(result, "check_fn", None)
            if check is not None:
                # Deferred checks from an earlier document must not execute
                # after a load, even if a later turn rebinds the global target.
                captured = _epoch

                def guarded_check():
                    if _blocked(captured):
                        return _error()
                    return check()
                return _server._ExecResult(result.response, guarded_check)
            return result

        server._execute_code = execute
        _records.append({"server": server, "original": original, "wrapper": execute, "endpoint": None})


def _pause():
    for record in _records:
        server = record["server"]
        listener = getattr(server._state, "sock", None)
        if listener is not None:
            record["endpoint"] = listener.getsockname()[:2]
            # Official stop closes accepted clients, queued writes and deferred
            # responses. No pre-load request stays queued for the next scene.
            server.stop()


def _resume():
    for record in _records:
        server, endpoint = record["server"], record["endpoint"]
        if endpoint is not None and not server.is_running():
            server.start(*endpoint)
            bpy = sys.modules.get("bpy")
            if bpy is not None and not bpy.app.background:
                poll = importlib.import_module(server.__package__ + ".execute_interactive").run
                if not bpy.app.timers.is_registered(poll):
                    bpy.app.timers.register(poll, first_interval=.1, persistent=True)


def before_file_load():
    global _epoch, _loading, _invalidated
    _main_thread()
    if _loading:
        return
    _loading = _invalidated = True
    _epoch = uuid.uuid4().hex
    _pause()


def after_file_load():
    global _loading
    _main_thread()
    _loading = False
    # Listener may answer with scene_target_changed while the old model turn
    # finishes other work. It cannot silently switch that turn to the new scene.
    _resume()


def bind_turn(context, addons=None):
    """Call immediately BEFORE sending an accepted new turn, never mid-turn."""
    global _turn_epoch, _invalidated
    _main_thread()
    if _loading:
        raise RuntimeError("Wait for Blender to finish loading its file")
    if addons is not None:
        install(addons)
    if not _records:
        raise RuntimeError("The official Blender bridge has no scene lifecycle guard")
    if _invalidated:
        # Flush old sockets/deferred callbacks again before fresh work is sent.
        _pause()
        _resume()
    if sum(bool(record["server"].is_running()) for record in _records) != 1:
        raise RuntimeError("Start exactly one guarded official Blender listener before sending a scene turn")
    _turn_epoch = _epoch
    _invalidated = False
    return target_context(context)


def target_context(context):
    _main_thread()
    scene = getattr(context, "scene", None)
    return {"scene_epoch": _epoch, "scene_loading": _loading,
            "scene_identity": scene.as_pointer() if scene is not None else None}


def register(bpy=None):
    global _handlers
    _main_thread()
    if _handlers is not None:
        return
    bpy = bpy or importlib.import_module("bpy")
    install(bpy.context.preferences.addons)

    @bpy.app.handlers.persistent
    def pre(_dummy):
        install(bpy.context.preferences.addons)
        before_file_load()

    @bpy.app.handlers.persistent
    def post(_dummy):
        after_file_load()

    bpy.app.handlers.load_pre.append(pre)
    bpy.app.handlers.load_post.append(post)
    # Failed file loads also need to restore listener availability, while the
    # invalidated epoch still rejects old work until an explicit fresh turn.
    failed = getattr(bpy.app.handlers, "load_post_fail", None)
    if failed is not None:
        failed.append(post)
    _handlers = (bpy, pre, post)


def unregister():
    global _handlers, _turn_epoch, _invalidated, _loading
    _main_thread()
    if _handlers is not None:
        bpy, pre, post = _handlers
        for collection, handler in ((bpy.app.handlers.load_pre, pre), (bpy.app.handlers.load_post, post),
                                    (getattr(bpy.app.handlers, "load_post_fail", []), post)):
            if handler in collection:
                collection.remove(handler)
        _handlers = None
    for record in _records:
        if record["server"]._execute_code is record["wrapper"]:
            record["server"]._execute_code = record["original"]
    _resume()
    _records.clear()
    _turn_epoch = None
    _invalidated = _loading = False
