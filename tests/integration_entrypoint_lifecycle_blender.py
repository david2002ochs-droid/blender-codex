"""Exercise the registered add-on entrypoint across a real unsaved-file load."""
from pathlib import Path
import sys
import bpy
import addon_utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import blender_codex as addon

class Client:
    closed = False
    def close(self):
        self.closed = True

assert addon_utils.enable("blender_codex", default_set=True) is not None
client = Client()
addon._session.client = client
addon._session.ready = True
addon._session.busy = True
addon._session.thread_id = "fixture-thread"
addon._session.messages.append({"role": "You", "text": "fixture"})
generation = addon._session.generation
bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
assert addon._session.client is client and not client.closed
assert addon._session.ready and addon._session.busy
assert addon._session.thread_id == "fixture-thread" and addon._session.messages
assert addon._session.generation == generation
addon.unregister()
assert client.closed
print("ENTRYPOINT_FILE_LOAD_PASS: client, busy turn, history and generation retained; unregister closes client")
