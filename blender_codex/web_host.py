"""Windows-only WebView2 child HWND host. This module never calls bpy.

WebHost(url, parent_hwnd=None) discovers a visible window of the current
Blender process unless supplied explicitly. update(x, y, width, height) uses
physical client-area pixels relative to that HWND, with a top-left origin,
and shows the child. hide()/show()/close() control the actual embedded HWND.
alive and error are read-only status properties; readiness is also exposed.

Protocol: UTF-8 JSON lines on redirected stdin: geometry {x,y,width,height},
hide, show, close ("type" key). stdout: ready {hwnd,parent_hwnd}, error {text}.
Diagnostic stdout events populate diagnostics, last_geometry, and navigation;
they never include the URL, its token, or chat content.
Owner exit or stdin EOF closes the helper. No TCP control port is opened.
"""

import ctypes
from collections import deque
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import urlsplit


def _validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1", "localhost")
            or not parsed.port or parsed.username or parsed.password):
        raise ValueError("WebView URL must use an explicit HTTP loopback origin")


def find_blender_window():
    """Find this process's sole visible, unowned Blender main window.

    This MVP cannot map bpy windows to native HWNDs. Refuse ambiguity instead
    of attaching to a foreground/first window with unrelated region geometry.
    Console windows, owned dialogs, and other programs are excluded.
    """
    if sys.platform != "win32":
        raise RuntimeError("Embedded WebView2 is supported only on Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def belongs(hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != os.getpid() or not user32.IsWindowVisible(hwnd):
            return False
        if user32.GetWindow(hwnd, 4):  # GW_OWNER: ignore owned/modal windows.
            return False
        class_name = ctypes.create_unicode_buffer(256)
        if not user32.GetClassNameW(hwnd, class_name, len(class_name)):
            return False
        return class_name.value == "GHOST_WindowClass"

    @callback_type
    def visit(hwnd, _param):
        if belongs(hwnd):
            windows.append(int(hwnd))
        return True

    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    if not user32.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if not windows:
        raise RuntimeError("No visible Blender main window found")
    if len(windows) > 1:
        raise RuntimeError("Embedded chat currently supports one Blender window; close additional Blender windows and retry")
    return windows[0]


class WebHost:
    def __init__(self, url, parent_hwnd=None, executable=None, user_data_dir=None):
        if sys.platform != "win32":
            raise RuntimeError("Embedded WebView2 is supported only on Windows")
        _validate_url(url)
        self.parent_hwnd = int(parent_hwnd or find_blender_window())
        binary = Path(executable) if executable else Path(__file__).parent / "native" / "WebHost.exe"
        if not binary.is_file():
            raise RuntimeError("WebView2 helper missing; run scripts/build-web-host.ps1")
        if user_data_dir is None:
            local = os.environ.get("LOCALAPPDATA")
            if not local:
                raise RuntimeError("LOCALAPPDATA is unavailable for the WebView2 profile")
            user_data_dir = Path(local) / "BlenderCodex" / "WebView2" / str(os.getpid())
        self._error = None
        self._ready = False
        self.diagnostics = deque(maxlen=40)
        self.last_geometry = None
        self.last_visibility = None
        self.navigation = None
        self.requested_width = None
        self.requested_bounds = None
        self.hwnd = None
        self._lock = threading.Lock()
        self._geometry = None
        self._visible = False
        self._process = subprocess.Popen(
            [str(binary.resolve()), str(self.parent_hwnd), str(os.getpid()), url,
             str(Path(user_data_dir).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", text=True, bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=str(binary.resolve().parent),
        )
        threading.Thread(target=self._read_status, name="BlenderCodex-WebView", daemon=True).start()

    @property
    def error(self):
        if self._error:
            return self._error
        code = self._process.poll()
        return "WebView2 helper exited (code {})".format(code) if code not in (None, 0) else None

    @property
    def alive(self):
        return self._process.poll() is None and self._error is None

    @property
    def ready(self):
        return self._ready and self.alive

    def start(self):
        """Compatibility hook: construction already starts the hidden helper."""
        return self

    @property
    def parent_client_size(self):
        """Return the parent client size in Blender's current DPI coordinate space.

        Scale Blender's window/region coordinates by client_size/window_size
        if necessary before passing them to update().
        """
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClientRect.restype = wintypes.BOOL
        rectangle = wintypes.RECT()
        if not user32.GetClientRect(self.parent_hwnd, ctypes.byref(rectangle)):
            raise ctypes.WinError(ctypes.get_last_error())
        return rectangle.right - rectangle.left, rectangle.bottom - rectangle.top

    def _read_status(self):
        try:
            for line in self._process.stdout:
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if event.get("type") == "ready":
                    self.hwnd = int(event["hwnd"])
                    self._ready = True
                elif event.get("type") == "error":
                    self._error = str(event.get("text", "WebView2 initialization failed"))
                elif event.get("type") == "diagnostic":
                    self.diagnostics.append(str(event.get("stage", "")))
                elif event.get("type") == "geometry":
                    self.last_geometry = event
                elif event.get("type") == "visibility":
                    self.last_visibility = event
                elif event.get("type") == "navigation":
                    self.navigation = event
                elif event.get("type") == "resize":
                    width = event.get("width")
                    if type(width) is int and 0 <= width <= 32768:
                        self.requested_width = width
                elif event.get("type") == "bounds_changed":
                    if all(type(event.get(key)) is int for key in ("x", "y", "width", "height")):
                        self.requested_bounds = event
        except (OSError, ValueError):
            pass
        finally:
            self._process.stdout.close()

    def _send(self, command):
        with self._lock:
            if not self.alive:
                return False
            try:
                self._process.stdin.write(json.dumps(command, ensure_ascii=True) + "\n")
                self._process.stdin.flush()
                return True
            except (OSError, ValueError):
                self._error = "WebView2 helper control pipe closed"
                return False

    def update(self, x, y, width, height):
        geometry = tuple(int(value) for value in (x, y, width, height))
        if geometry[2] <= 0 or geometry[3] <= 0:
            self.hide()
            return
        if geometry != self._geometry or not self._visible:
            if self._send(dict(type="geometry", **dict(zip(("x", "y", "width", "height"), geometry)))):
                self._geometry = geometry
                self._visible = True

    def hide(self):
        if self._visible and self._send({"type": "hide"}):
            self._visible = False

    def show(self):
        if not self._visible and self._geometry and self._send({"type": "show"}):
            self._visible = True

    def close(self):
        # Do not block Blender's UI thread while WebView2 disposes its processes.
        self._send({"type": "close"})
        with self._lock:
            try:
                self._process.stdin.close()
            except (OSError, ValueError):
                pass

        def reap():
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        threading.Thread(target=reap, name="BlenderCodex-WebView-close", daemon=True).start()
