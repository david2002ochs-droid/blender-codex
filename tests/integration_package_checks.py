"""Meaningful negative checks for the independent package inspector."""
import importlib.util
from pathlib import Path
import tempfile
import re
import shutil
import subprocess
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("package_inspector", Path(__file__).with_name("integration_package.py"))
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


class PackagingChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "source"
        self.archive = self.folder / "plugin.zip"
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            (self.folder / name).write_text("fixture notice", encoding="utf-8")
        files = {"__init__.py": "# fixture", "instructions.txt": "fixture instructions",
                 "web/index.html": '<script type="module" src="./assets/main.js"></script><link rel="stylesheet" href="./assets/style.css">',
                 "web/assets/main.js": 'import "./chunk.js";', "web/assets/chunk.js": 'export const fixture=1;',
                 "web/assets/style.css": '@font-face {font-family:fixture;src:url("./font.woff2")}',
                 "web/assets/font.woff2": "font fixture", "web/THIRD_PARTY_NOTICES.txt": "fixture license"}
        files.update({"native/" + name: "native fixture" for name in inspector.NATIVE})
        for relative, text in files.items():
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def build(self, omit=(), extras=None):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                if name not in omit:
                    archive.write(self.folder / name, "blender_codex/" + name)
            for path in self.source.rglob("*"):
                if path.is_file() and path.relative_to(self.source).as_posix() not in omit:
                    archive.write(path, "blender_codex/" + path.relative_to(self.source).as_posix())
            for name, text in (extras or {}).items():
                archive.writestr(name, text)
        return inspector.inspect(self.archive, self.source)

    def test_nested_chunks_fonts_and_license_pass(self):
        self.assertTrue(self.build()["passed"])

    def test_missing_nested_font_is_rejected(self):
        result = self.build(omit={"web/assets/font.woff2"})
        self.assertFalse(result["passed"])
        self.assertTrue(any("font.woff2" in error for error in result["errors"]))

    def test_missing_project_license_is_rejected(self):
        result = self.build(omit={"LICENSE"})
        self.assertFalse(result["passed"])
        self.assertTrue(any("blender_codex/LICENSE" in error for error in result["errors"]))

    def test_missing_imported_chunk_is_rejected(self):
        result = self.build(omit={"web/assets/chunk.js"})
        self.assertFalse(result["passed"])
        self.assertTrue(any("Missing local dependency" in error for error in result["errors"]))

    def test_bundled_language_grammar_keywords_are_not_imports(self):
        (self.source / "web/assets/chunk.js").write_text('const grammar={"import":":{","from":"},{"};', encoding="utf-8")
        self.assertTrue(self.build()["passed"])

    def test_stale_package_bytes_are_rejected(self):
        self.build()
        (self.source / "instructions.txt").write_text("new prompt", encoding="utf-8")
        result = inspector.inspect(self.archive, self.source)
        self.assertTrue(any("Archive/source mismatch" in error for error in result["errors"]))

    def test_secret_development_and_escaping_entries_rejected(self):
        for name in ("blender_codex/.env", "blender_codex/web/node_modules/pkg/index.js", "../outside.txt"):
            with self.subTest(name=name):
                self.assertFalse(self.build(extras={name: "fixture"})["passed"])

    def test_remote_runtime_dependency_rejected(self):
        (self.source / "web/index.html").write_text('<script src="https://example.invalid/runtime.js"></script>', encoding="utf-8")
        result = self.build()
        self.assertTrue(any("Nonlocal runtime dependency" in error for error in result["errors"]))

    def test_real_powershell_packager_in_isolated_fixture(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell is required for the real packaging script check")
        project = self.folder / "project"
        destination = project / "blender_codex"
        shutil.copytree(self.source, destination)
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            shutil.copyfile(self.folder / name, project / name)
        scripts = project / "scripts"
        scripts.mkdir()
        script = scripts / "package.ps1"
        shutil.copyfile(Path(__file__).resolve().parents[1] / "scripts/package.ps1", script)
        # Populate the packager's declared required files while independently
        # checking implicit nested assets/chunks/fonts and failure atomicity.
        declaration = re.search(r"\$requiredFiles\s*=\s*@\((.*?)\)", script.read_text(encoding="utf-8"), re.S)
        self.assertIsNotNone(declaration)
        for name in re.findall(r"'([^']+)'", declaration.group(1)):
            file = destination / name
            if not file.exists():
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("# fixture", encoding="utf-8")
        command = [shell, "-NoProfile", "-File", str(script)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        archive = project / "dist/blender_codex.zip"
        inspection = inspector.inspect(archive, destination)
        self.assertTrue(inspection["passed"], inspection["errors"])
        previous = archive.read_bytes()
        (destination / "context.py").unlink()
        failed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(previous, archive.read_bytes(), "Failed build replaced a previously usable package")


if __name__ == "__main__":
    unittest.main()
