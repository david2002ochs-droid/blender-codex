"""Check the packaged prompt example against Blender and the pinned executor.

Run with Blender --background --factory-startup --python this_file. Requires
the project-local official source checkout. No model, network or user file I/O.
"""
from pathlib import Path
import json
import os
import re
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / ".runtime/official-mcp/source/addon"
if not source.is_dir():
    raise RuntimeError("Prepare the official MCP source before this opt-in smoke test.")
sys.path.insert(0, str(source))
from blender_mcp_addon.mcp_to_blender_server import _execute_code

prompt = (ROOT / "blender_codex/instructions.txt").read_text(encoding="utf-8")
examples = re.findall(r"```python\n(.*?)```", prompt, re.DOTALL)
assert examples, "No executable prompt examples found"
cube = bpy.data.objects["Cube"]
before = list(cube.dimensions)
for example in examples:
    execution = _execute_code(example, strict_json=True)
    # The official return is an _ExecResult named tuple.
    payload = execution[0]
    assert payload["status"] == "ok", payload
    assert payload["result"]["process_id"] == os.getpid()
    assert payload["result"]["filepath"] == ""
    assert payload["result"]["object"]["name"] == "Cube"
    assert payload["result"]["object"]["dimensions"] == before
    json.dumps(payload["result"], allow_nan=False)
assert list(cube.dimensions) == before
assert not bpy.data.filepath
print("PROMPT_EXECUTOR_PASS: prompt example runs with fresh imports and JSON result in official executor")
