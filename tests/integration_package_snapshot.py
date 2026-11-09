"""Freeze actual package inputs, reject concurrent edits, then package that copy.

The resulting ZIP is an integration proof artifact under .runtime, not a claim
of an installed or live-model-tested release. No product file is modified.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("snapshot_inspector", Path(__file__).with_name("integration_package.py"))
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def inputs():
    files = list((ROOT / "blender_codex").glob("*.py"))
    files += [ROOT / "blender_codex/instructions.txt", ROOT / "scripts/package.ps1"]
    files += [p for p in (ROOT / "blender_codex/web").rglob("*") if p.is_file() and p.suffix.lower() in inspector.WEB_EXTENSIONS]
    files += [ROOT / "blender_codex/native" / name for name in inspector.NATIVE]
    files += [ROOT / name for name in ("frontend/vendor/deepblick/SOURCE.json", "frontend/vendor/deepblick/LICENSE", "frontend/BUILD.json")]
    return {p.relative_to(ROOT).as_posix(): p for p in files if p.is_file()}


def digest(files):
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}


def main():
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise RuntimeError("PowerShell required")
    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = ROOT / ".runtime" / ("deepblick-package-proof-" + started)
    files = inputs()
    before = digest(files)
    for relative, source in files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    after = digest(inputs())
    copied = digest({name: destination / name for name in files})
    stable = before == after == copied
    receipt = {"started_utc": started, "stable_copy": stable, "original_sha256": before,
               "sha256_after_copy": after, "frozen_root": str(destination), "passed": False,
               "scope": "actual frozen package inputs; no install, live UI, model call or paid job"}
    if stable:
        build = subprocess.run([shell, "-NoProfile", "-File", str(destination / "scripts/package.ps1")],
                               capture_output=True, text=True, timeout=45)
        receipt["build_exit_code"] = build.returncode
        if build.returncode == 0:
            inspection = inspector.inspect(destination / "dist/blender_codex.zip", destination / "blender_codex")
            receipt["inspection"] = inspection
            receipt["passed"] = inspection["passed"]
        else:
            receipt["build_error"] = build.stdout + build.stderr
    output = ROOT / ".runtime/deepblick-package-proof-receipt.json"
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("FROZEN_ACTUAL_PACKAGE", "PASS" if receipt["passed"] else "FAIL", "stable=" + str(stable))
    for error in receipt.get("inspection", {}).get("errors", []):
        print("FAIL", error)
    if "build_error" in receipt:
        print(receipt["build_error"])
    print("Receipt:", output)
    return 2 if not stable else 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
