"""Inspect an add-on ZIP against its source snapshot and local web dependencies.

No Blender, network, model call or installer is started. Every required package
byte is compared with current sources; callers should additionally use
integration_snapshot.py to reject concurrent changes during packaging/tests.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ("WebHost.exe", "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll",
          "WebView2Loader.dll", "WebView2-LICENSE.txt")
WEB_EXTENSIONS = {".html", ".js", ".mjs", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif",
                  ".ico", ".avif", ".woff", ".woff2", ".ttf", ".otf", ".json", ".wasm", ".txt", ".md"}


class HTMLReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        key = "src" if tag in ("script", "img", "source", "iframe") else "href" if tag == "link" else None
        if key and attrs.get(key):
            self.references.append(attrs[key])


def inspect(archive, source_root=ROOT / "blender_codex"):
    errors = []
    source = {}
    for path in source_root.glob("*.py"):
        source[path.name] = path
    source["instructions.txt"] = source_root / "instructions.txt"
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        source[name] = source_root.parent / name
    for path in (source_root / "web").rglob("*"):
        if path.is_file() and path.suffix.lower() in WEB_EXTENSIONS:
            source[path.relative_to(source_root).as_posix()] = path
    for name in NATIVE:
        source["native/" + name] = source_root / "native" / name
    ui_source = source_root.parent / "frontend/vendor/deepblick/SOURCE.json"
    if ui_source.is_file():
        source["web/deepblick-source.json"] = ui_source
        source["web/deepblick-build.json"] = source_root.parent / "frontend/BUILD.json"
        source["web/DEEPBLICK-LICENSE.txt"] = source_root / "web/DEEPBLICK-LICENSE.txt"
    hashes = {}
    with zipfile.ZipFile(archive) as package:
        entries = package.namelist()
        names = set(entries)
        if len(entries) != len(names):
            errors.append("Duplicate archive entry names")
        for name in entries:
            parts = PurePosixPath(name).parts
            if (not name.startswith("blender_codex/") or ".." in parts or "\\" in name
                    or any(p in (".runtime", "node_modules", "__pycache__", ".git") for p in parts)
                    or any(p.startswith(".env") for p in parts) or name.endswith(".pyc")):
                errors.append("Unsafe/development archive entry: " + name)
        for relative, path in source.items():
            entry = "blender_codex/" + relative
            if not path.is_file():
                errors.append("Required source missing: " + relative)
                continue
            if entry not in names:
                errors.append("Required archive file missing: " + entry)
                continue
            data = package.read(entry)
            digest = hashlib.sha256(data).hexdigest()
            hashes[entry] = digest
            if digest != hashlib.sha256(path.read_bytes()).hexdigest():
                errors.append("Archive/source mismatch: " + entry)
        for name in sorted(names):
            if not name.startswith("blender_codex/web/"):
                continue
            suffix = PurePosixPath(name).suffix.lower()
            if suffix not in (".html", ".css", ".js", ".mjs"):
                continue
            text = package.read(name).decode("utf-8")
            if "C:\\Users\\david\\" in text or "C:/Users/david/" in text:
                errors.append("Developer-machine path in web asset: " + name)
            references = []
            if suffix == ".html":
                parser = HTMLReferences()
                parser.feed(text)
                references += parser.references
            elif suffix == ".css":
                references += [match[1] for match in re.findall(r"url\(\s*(['\"]?)(.*?)\1\s*\)", text)]
            elif suffix in (".js", ".mjs"):
                # Do not mistake syntax-highlighter tables such as
                # {"import": ..., "from": ...} inside bundled grammar data for
                # executable module imports. Static module declarations occur
                # at statement starts; emitted bundle inputs are also compared
                # byte-for-byte above, independent of this reference check.
                references += re.findall(r"(?m)^\s*import\s*['\"]([^'\"\s\\]+)['\"]", text)
                references += re.findall(r"(?m)^\s*(?:import|export)\s+[^'\";\n]+\s+from\s*['\"]([^'\"\s\\]+)['\"]", text)
                references += re.findall(r"\bimport\s*\(\s*['\"]([^'\"\s\\]+)['\"]\s*\)", text)
            for reference in references:
                url = urlsplit(reference)
                if url.scheme in ("data", "blob") or not url.path:
                    continue
                if url.scheme or url.netloc:
                    errors.append("Nonlocal runtime dependency in " + name + ": " + reference)
                    continue
                if suffix in (".js", ".mjs") and not url.path.startswith((".", "/")):
                    errors.append("Unbundled bare module import in " + name + ": " + reference)
                    continue
                path = unquote(url.path)
                target = (PurePosixPath("blender_codex/web") / path.lstrip("/")) if path.startswith("/") else (PurePosixPath(name).parent / path)
                normalized = []
                for part in target.parts:
                    if part == "..":
                        if normalized:
                            normalized.pop()
                    elif part != ".":
                        normalized.append(part)
                target_name = "/".join(normalized)
                if target_name not in names:
                    errors.append("Missing local dependency from " + name + ": " + reference)
        if ui_source.is_file():
            provenance = json.loads(ui_source.read_text(encoding="utf-8"))
            if provenance.get("commit") != "2f3f5d304d0bd3ccc9f866dab4799d501d3d2c65":
                errors.append("Deepblick source revision does not match the requested handoff pin")
            license_source = ui_source.parent / "LICENSE"
            license_entry = "blender_codex/web/DEEPBLICK-LICENSE.txt"
            if license_entry in names and package.read(license_entry) != license_source.read_bytes():
                errors.append("Deepblick MIT source license differs from the vendored upstream license")
    return {"checked_utc": datetime.now(timezone.utc).isoformat(),
            "archive": str(archive.resolve()), "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "source_root": str(source_root.resolve()), "entry_count": len(entries),
            "checked_file_sha256": hashes, "errors": errors, "passed": not errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "dist/blender_codex.zip")
    parser.add_argument("--source-root", type=Path, default=ROOT / "blender_codex")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.archive, args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for error in result["errors"]:
        print("FAIL", error)
    print("PACKAGE_CHECK", "PASS" if result["passed"] else "FAIL", "entries=" + str(result["entry_count"]))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
