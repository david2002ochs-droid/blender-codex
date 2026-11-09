"""Apply a pinned, one-line Windows MCP stdio compatibility patch.

The official source checkout stays untouched. Only the installed helper with
an exact known upstream hash is accepted; repeating the patch is safe.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
import tempfile

PATCH = Path(__file__).with_name("blender-mcp-cli-stdin.patch")
PATCH_SHA256_LF = "6eeb962ff8df6986d5e7fd8237e83475d273f2906a730edc55b6583c1853b04f"
HASHES = {
    "9f2e0e86d889c445bf3c76ba84c91ed7d53a5b22eed85e55a6a7798ceb0e1eca":
        ("d74f9cac99cd723accd0e087a23e45870047e7328acefc21a6efbc93e5fdbb39", b"\r\n"),
    "e77e7b967d021f817a19d9269d3bf44068559aed7487c326eab8c7f3ab1187a3":
        ("5a608f16c449f1eb4c46fde9092f8fdc08b608b73f29980c8a9ad6c7f45533cc", b"\n"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply(path):
    if sha(PATCH.read_bytes().replace(b"\r\n", b"\n")) != PATCH_SHA256_LF:
        raise ValueError("Compatibility patch file does not match its pinned hash")
    data = path.read_bytes()
    current = sha(data)
    for original, (patched, newline) in HASHES.items():
        if current == patched:
            return {"id": "blender-mcp-cli-stdin", "patch_sha256_lf": PATCH_SHA256_LF,
                    "original_sha256": original, "installed_sha256": patched, "already_applied": True}
        if current != original:
            continue
        needle = b"            capture_output=True," + newline
        replacement = b"            stdin=subprocess.DEVNULL," + newline + needle
        if data.count(needle) != 1:
            raise ValueError("Unexpected upstream subprocess invocation")
        result = data.replace(needle, replacement, 1)
        if sha(result) != patched:
            raise ValueError("Generated compatibility patch has an unexpected hash")
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
                temp_name = temp.name
                temp.write(result)
            os.replace(temp_name, path)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
        return {"id": "blender-mcp-cli-stdin", "patch_sha256_lf": PATCH_SHA256_LF,
                "original_sha256": original, "installed_sha256": patched, "already_applied": False}
    raise ValueError("Installed Blender MCP helper differs from the pinned source; refusing to patch")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, help="explicit file, for isolated regression tests")
    args = parser.parse_args()
    if args.file is None:
        spec = importlib.util.find_spec("blmcp.tools_helpers.blender_cli")
        if spec is None or spec.origin is None:
            raise RuntimeError("Installed Blender MCP helper not found")
        path = Path(spec.origin).resolve()
        if not path.is_relative_to(Path(sys.prefix).resolve()):
            raise RuntimeError("MCP helper is outside this virtual environment")
    else:
        path = args.file
    print(json.dumps(apply(path)))


if __name__ == "__main__":
    main()
