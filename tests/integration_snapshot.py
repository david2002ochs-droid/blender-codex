"""Run a check with before/after source hashes; changed sources invalidate evidence.

Example: python tests/integration_snapshot.py --output .runtime/check.json -- python -m unittest discover -s tests
No shell invocation, installs, model requests, or product writes are performed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def snapshot(root=ROOT, scope="all"):
    files = {}
    if scope == "lifecycle":
        for name in ("blender_codex/web_ui.py", "blender_codex/scene_lifecycle.py", "blender_codex/panel_layout.py",
                     "tests/test_view_lifecycle.py", "tests/test_scene_lifecycle.py"):
            files[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        return files
    if scope == "backend":
        for name in ("blender_codex/codex_client.py", "blender_codex/session_state.py", "blender_codex/request_forms.py",
                     "blender_codex/official_backend.py", "blender_codex/instructions.txt", "tests/integration_transport_projection.py"):
            path = root / name
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return files
    for folder in ("blender_codex", "frontend", "native", "scripts", "tests", "prompts"):
        for directory, directories, names in os.walk(root / folder):
            directories[:] = sorted(name for name in directories if name not in ("node_modules", ".git", "__pycache__"))
            for name in sorted(names):
                path = Path(directory) / name
                if path.suffix == ".pyc":
                    continue
                files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("ARCHITECTURE.md", "README.md"):
        path = root / name
        if path.exists():
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", choices=("all", "backend", "lifecycle"), default="all")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    command = options.command
    if command[:1] == ["--"]:
        command = command[1:]
    started = datetime.now(timezone.utc).isoformat()
    before = snapshot(scope=options.scope)
    result = subprocess.run(command, cwd=ROOT, check=False) if command else None
    after = snapshot(scope=options.scope)
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    receipt = {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "scope": options.scope,
               "command": command, "exit_code": None if result is None else result.returncode,
               "stable_snapshot": not changed, "changed_files": changed,
               "sha256_before": before, "sha256_after": after}
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("SNAPSHOT_RECEIPT", options.output, "stable=" + str(not changed))
    if changed:
        print("Evidence invalidated by source changes:", ", ".join(changed))
        return 2
    return 0 if result is None else result.returncode


if __name__ == "__main__":
    sys.exit(main())
