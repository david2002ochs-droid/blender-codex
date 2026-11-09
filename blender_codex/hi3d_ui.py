"""Native Hi3D controls; session fields or local .env credentials read on request."""
import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import textwrap

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, PointerProperty, StringProperty

_events = queue.Queue()
_thread = None
_cancel = threading.Event()
_generation = 0
_registered = False
_registered_classes = []
_status = "Ready"
_error = ""
_balance = ""
_record = {}
_record_path = None


def _settings(context):
    return context.window_manager.hi3d_settings


def _busy():
    return _thread is not None and _thread.is_alive()


def _save(record, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _read():
    try:
        value = json.loads(Path(_record_path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _redraw():
    for wm in bpy.data.window_managers:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()


def _drain():
    global _status, _error, _balance, _record
    if not _registered:
        return None
    changed = False
    for _ in range(100):
        try:
            generation, kind, value = _events.get_nowait()
        except queue.Empty:
            break
        if generation != _generation:
            continue
        changed = True
        if kind == "status":
            _status = value
        elif kind == "error":
            _error = value
            _status = "Error — task ID retained" if _record.get("task_id") else "Operation failed"
        elif kind == "balance":
            _balance = str(value)
            _status = "Access verified"
        elif kind == "job":
            _record = value
            for wm in bpy.data.window_managers:
                wm.hi3d_settings.task_id = str(value.get("task_id", ""))
        elif kind == "stopped":
            _status = "Local polling stopped; provider job may continue and incur charges"
    if changed:
        _redraw()
    return 0.2


def _launch(context, action, *, snapshot=None):
    """Snapshot every Blender value before starting a worker; no bpy on workers."""
    global _thread, _cancel, _error, _status
    if _busy():
        raise ValueError("Wait for the current network operation to finish")
    settings = _settings(context)
    from .hi3d_config import load_credentials
    from .context import project_directory
    entered = (settings.client_id.strip(), settings.client_secret.strip())
    client_id, secret = load_credentials(explicit=entered if any(entered) else None,
                                        cwd=project_directory(),
                                        env_file=bpy.path.abspath(settings.env_file) if settings.env_file else None)
    if not client_id or not secret:
        raise ValueError("Enter Hi3D AK/SK in the local .env file or provider fields.")
    from .hi3d import Hi3DClient, Hi3DError
    image = bpy.path.abspath(settings.image_path)
    output = bpy.path.abspath(settings.output_directory) if settings.output_directory else str(Path(_record_path).parent)
    resolution, pbr = settings.resolution, settings.pbr
    record = dict(_record)
    task_id = settings.task_id.strip() or str(record.get("task_id", ""))
    if action == "submit":
        if snapshot != (image, resolution, pbr):
            raise ValueError("Settings changed after confirmation; open Generate again")
        if not Path(image).is_file():
            raise ValueError("Choose an existing image file")
    if action == "resume" and not task_id:
        record = _read()
        task_id = str(record.get("task_id", ""))
        if not task_id:
            raise ValueError("Enter a task ID or create a task first")
    cancel = threading.Event()
    _cancel = cancel
    generation = _generation
    record_path = str(_record_path)
    _error = ""
    _status = "Checking access…" if action == "balance" else "Starting…"

    def emit(kind, value):
        _events.put((generation, kind, value))

    def run():
        try:
            client = Hi3DClient(client_id, secret)
            if action == "balance":
                emit("balance", client.balance())
                return
            job = dict(record) if record.get("task_id") == task_id else {}
            Path(output).mkdir(parents=True, exist_ok=True)
            if action == "submit":
                # Verify metadata storage before a paid call. Never retry submit.
                _save(record, record_path)
                emit("status", "Submitting paid task…")
                new_id = client.submit(image, resolution=resolution, pbr=pbr)
                job = {"task_id": str(new_id), "model": "hi3dv3.0", "resolution": resolution,
                       "pbr": pbr, "image": image, "state": "created"}
            else:
                job["task_id"] = task_id
                job.setdefault("model", "hi3dv3.0")
            emit("job", dict(job))
            _save(job, record_path)
            while not cancel.is_set():
                result = client.query(job["task_id"])
                state = str(result.get("state", "unknown"))
                job["state"] = state
                emit("status", state)
                emit("job", dict(job))
                _save(job, record_path)
                if state == "failed":
                    emit("error", "Provider reports task failed. Resume queries the same ID; it does not resubmit.")
                    return
                if state == "success":
                    if cancel.is_set():
                        break
                    url = result.get("url")
                    if not url:
                        raise ValueError("Completed task has no GLB download URL; resume later")
                    emit("status", "success — downloading GLB…")
                    name = "hi3d_" + hashlib.sha256(job["task_id"].encode()).hexdigest()[:20] + ".glb"
                    destination = str(Path(output) / name)
                    local_path = client.download(url, destination)
                    job["glb_path"] = str(local_path)
                    _save(job, record_path)
                    emit("job", dict(job))
                    emit("status", "success — GLB ready for explicit import")
                    return
                if cancel.wait(3):
                    break
            emit("stopped", None)
        except Hi3DError as exc:
            emit("error", str(exc))
        except Exception:
            # Do not surface arbitrary network exceptions containing signed URLs or secrets.
            emit("error", "Operation failed. Check the image, output folder and connection. Known task ID is retained; no paid retry was made.")

    _thread = threading.Thread(target=run, name="Hi3D worker", daemon=True)
    _thread.start()


@persistent
def _load_pre(_dummy):
    global _generation, _status, _error, _balance, _record
    _generation += 1
    _cancel.set()
    _status = "File changed — resume a saved task explicitly"
    _error = _balance = ""
    _record = {}
    for wm in bpy.data.window_managers:
        if hasattr(wm, "hi3d_settings"):
            wm.hi3d_settings.client_id = ""
            wm.hi3d_settings.client_secret = ""


@persistent
def _load_post(_dummy):
    global _record
    _record = _read()
    for wm in bpy.data.window_managers:
        wm.hi3d_settings.client_id = ""
        wm.hi3d_settings.client_secret = ""
        wm.hi3d_settings.task_id = str(_record.get("task_id", ""))


class HI3D_Settings(bpy.types.PropertyGroup):
    env_file: StringProperty(name="Credentials .env", subtype="FILE_PATH", options={"SKIP_SAVE"})
    client_id: StringProperty(name="CLIENT_ID", subtype="PASSWORD", options={"SKIP_SAVE"})
    client_secret: StringProperty(name="CLIENT_SECRET", subtype="PASSWORD", options={"SKIP_SAVE"})
    image_path: StringProperty(name="Image", subtype="FILE_PATH", options={"SKIP_SAVE"})
    output_directory: StringProperty(name="Output folder", subtype="DIR_PATH", options={"SKIP_SAVE"})
    resolution: EnumProperty(name="Quality", items=[("2048quality", "Quality", ""), ("2048master", "Master", "")], default="2048quality", options={"SKIP_SAVE"})
    pbr: BoolProperty(name="PBR materials", default=True, options={"SKIP_SAVE"})
    task_id: StringProperty(name="Task ID", options={"SKIP_SAVE"})


class HI3D_OT_console(bpy.types.Operator):
    bl_idname = "hi3d.console"
    bl_label = "Set up access — Hi3D console"

    def execute(self, context):
        bpy.ops.wm.url_open(url="https://platform.hi3d.ai")
        return {"FINISHED"}


class HI3D_OT_access(bpy.types.Operator):
    bl_idname = "hi3d.access"
    bl_label = "Test access / balance"

    @classmethod
    def poll(cls, context):
        return not _busy()

    def execute(self, context):
        try:
            _launch(context, "balance")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class HI3D_OT_generate(bpy.types.Operator):
    bl_idname = "hi3d.generate"
    bl_label = "Generate (paid)"
    bl_description = "Upload the image and create one paid Hi3D task after confirmation"
    confirmed_image: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    confirmed_resolution: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    confirmed_pbr: BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return not _busy()

    def invoke(self, context, event):
        settings = _settings(context)
        self.confirmed_image = bpy.path.abspath(settings.image_path)
        self.confirmed_resolution = settings.resolution
        self.confirmed_pbr = settings.pbr
        if not Path(self.confirmed_image).is_file():
            self.report({"ERROR"}, "Choose an existing image file")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=470, confirm_text="Upload and pay")

    def draw(self, context):
        layout = self.layout
        _wrap(layout, "Image: " + self.confirmed_image, 62)
        layout.label(text="Model: hi3dv3.0 · geometry + texture · GLB")
        layout.label(text="Quality: " + self.confirmed_resolution + " · PBR: " + str(self.confirmed_pbr))
        layout.label(text="Estimated cost: {} credits".format(_estimate(self.confirmed_resolution, self.confirmed_pbr)))
        _wrap(layout, "Provider estimate, not a binding quote. This uploads your image and starts one paid task.", 62)
        if _record.get("task_id"):
            _wrap(layout, "A saved task already exists. This starts a NEW paid task and replaces the saved job record. Copy the old task ID to keep it.", 62)

    def execute(self, context):
        # EXEC_DEFAULT without the confirmation snapshot cannot create a paid job.
        if not self.confirmed_image:
            self.report({"ERROR"}, "Use Generate to review and confirm image and cost first")
            return {"CANCELLED"}
        try:
            _launch(context, "submit", snapshot=(self.confirmed_image, self.confirmed_resolution, self.confirmed_pbr))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class HI3D_OT_resume(bpy.types.Operator):
    bl_idname = "hi3d.resume"
    bl_label = "Resume / query task"
    bl_description = "Query the same task ID without submitting or paying for another task"

    @classmethod
    def poll(cls, context):
        return not _busy()

    def execute(self, context):
        try:
            _launch(context, "resume")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class HI3D_OT_stop(bpy.types.Operator):
    bl_idname = "hi3d.stop"
    bl_label = "Stop local polling"
    bl_description = "Only stops local polling; the paid provider task can continue and incur charges"

    def execute(self, context):
        global _status
        _cancel.set()
        _status = "Stopping local polling; provider job may continue and incur charges"
        return {"FINISHED"}


class HI3D_OT_restore(bpy.types.Operator):
    bl_idname = "hi3d.restore"
    bl_label = "Restore saved task ID"
    bl_description = "Read the latest locally saved job, without contacting Hi3D"

    @classmethod
    def poll(cls, context):
        return not _busy()

    def execute(self, context):
        global _record
        _record = _read()
        _settings(context).task_id = str(_record.get("task_id", ""))
        if not _record.get("task_id"):
            self.report({"INFO"}, "No saved task ID found")
        return {"FINISHED"}


class HI3D_OT_import(bpy.types.Operator):
    bl_idname = "hi3d.import_glb"
    bl_label = "Import downloaded GLB"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (not _busy() and bool(_record.get("glb_path"))
                and _settings(context).task_id.strip() == _record.get("task_id"))

    def execute(self, context):
        path = _record.get("glb_path", "")
        if not Path(path).is_file():
            self.report({"ERROR"}, "Downloaded GLB is missing; resume to download again")
            return {"CANCELLED"}
        before = set(bpy.data.objects)
        try:
            result = bpy.ops.import_scene.gltf(filepath=path)
            if "FINISHED" not in result:
                return {"CANCELLED"}
            for obj in set(bpy.data.objects) - before:
                obj["hi3d_provider"] = "Hi3D"
                obj["hi3d_model"] = _record.get("model", "hi3dv3.0")
                obj["hi3d_task_id"] = _record.get("task_id", "")
                obj["hi3d_resolution"] = _record.get("resolution", "unknown")
                if "pbr" in _record:
                    obj["hi3d_pbr"] = bool(_record["pbr"])
        except Exception:
            self.report({"ERROR"}, "GLB import failed; the download and task ID are retained")
            return {"CANCELLED"}
        return {"FINISHED"}


def _estimate(resolution, pbr):
    from .hi3d import estimate_credits
    return estimate_credits(resolution=resolution, pbr=pbr)


def _wrap(layout, text, width):
    for paragraph in str(text).splitlines() or [""]:
        for line in textwrap.wrap(paragraph, max(12, width)) or [""]:
            layout.label(text=line)


class HI3D_PT_panel(bpy.types.Panel):
    bl_label = "Hi3D Image to 3D"
    bl_idname = "HI3D_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "3D Providers"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = _settings(context)
        width = max(12, int(context.region.width / (7 * max(context.preferences.system.ui_scale, 0.5))) - 5)
        layout.operator("hi3d.console")
        layout.prop(settings, "env_file")
        layout.prop(settings, "client_id")
        layout.prop(settings, "client_secret")
        has_credentials = bool((settings.client_id.strip() or os.environ.get("HI3D_CLIENT_ID"))
                               and (settings.client_secret.strip() or os.environ.get("HI3D_CLIENT_SECRET")))
        _wrap(layout, "Ready — access not yet verified" if has_credentials else "Credentials are read from .env when requested; access not yet verified.", width)
        _wrap(layout, "Fields are session-only. Also reads local .env or HI3D environment variables.", width)
        layout.operator("hi3d.access")
        if _balance:
            layout.label(text="Balance: " + _balance + " credits")
        column = layout.column()
        column.enabled = not _busy()
        column.prop(settings, "image_path")
        column.prop(settings, "output_directory")
        column.prop(settings, "resolution")
        column.prop(settings, "pbr")
        column.label(text="Model: hi3dv3.0 · GLB")
        column.label(text="Estimated: {} credits".format(_estimate(settings.resolution, settings.pbr)))
        column.operator("hi3d.generate", icon="PLAY")
        layout.prop(settings, "task_id")
        layout.operator("hi3d.restore")
        layout.operator("hi3d.resume")
        layout.operator("hi3d.stop")
        _wrap(layout, "Stop affects local polling only; the provider job may continue and incur charges.", width)
        _wrap(layout, "Status: " + _status, width)
        if _error:
            box = layout.box()
            box.alert = True
            _wrap(box, _error, width)
        if _record.get("glb_path"):
            _wrap(layout, "Downloaded GLB: " + str(_record["glb_path"]), width)
        layout.operator("hi3d.import_glb", icon="IMPORT")


_CLASSES = (HI3D_Settings, HI3D_OT_console, HI3D_OT_access, HI3D_OT_generate,
            HI3D_OT_resume, HI3D_OT_stop, HI3D_OT_restore, HI3D_OT_import, HI3D_PT_panel)


def _initialize():
    # addon_utils.enable() restricts bpy.data during register(). Run afterwards.
    if _registered:
        for wm in bpy.data.window_managers:
            if not wm.hi3d_settings.task_id:
                wm.hi3d_settings.task_id = str(_record.get("task_id", ""))
    return None


def register():
    global _registered, _record_path, _record
    if _registered:
        return
    try:
        datafiles = bpy.utils.user_resource("DATAFILES", path="blender_codex", create=False)
        if not datafiles:
            datafiles = str(Path(bpy.utils.resource_path("USER")) / "datafiles" / "blender_codex")
        # Do not create folders during enable; a worker verifies storage before submit.
        _record_path = str(Path(datafiles) / "hi3d_job.json")
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
            _registered_classes.append(cls)
        bpy.types.WindowManager.hi3d_settings = PointerProperty(type=HI3D_Settings)
        _record = _read()
        bpy.app.handlers.load_pre.append(_load_pre)
        bpy.app.handlers.load_post.append(_load_post)
        _registered = True
        bpy.app.timers.register(_initialize, first_interval=0.0)
        bpy.app.timers.register(_drain, first_interval=0.2, persistent=True)
    except Exception:
        unregister()
        raise


def unregister():
    global _registered, _generation
    _registered = False
    _generation += 1
    _cancel.set()
    for timer in (_initialize, _drain):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    for handlers, callback in ((bpy.app.handlers.load_pre, _load_pre), (bpy.app.handlers.load_post, _load_post)):
        if callback in handlers:
            handlers.remove(callback)
    if hasattr(bpy.types.WindowManager, "hi3d_settings"):
        del bpy.types.WindowManager.hi3d_settings
    while _registered_classes:
        bpy.utils.unregister_class(_registered_classes.pop())
