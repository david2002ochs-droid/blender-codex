"""Launch settings for the pinned official Blender Lab MCP, without bpy.

Setup installs the official source into a project-local virtual environment.
An installed add-on can locate that prepared runtime through the explicit
BLENDER_CODEX_OFFICIAL_RUNTIME environment variable, or an absolute Python path
in its connection preferences. This module never installs or changes settings.
"""
import json
import os
from pathlib import Path

SOURCE_URL = "https://projects.blender.org/lab/blender_mcp.git"
SOURCE_REVISION = "dbbf836ad4b1025f14a2b3b504c43903f39e0b04"
SOURCE_VERSION = "1.0.2"
SOURCE_LICENSE = "GPL-3.0-or-later"
DEFAULT_RUNTIME_ROOT = Path(os.environ.get(
    "BLENDER_CODEX_OFFICIAL_RUNTIME", Path(__file__).resolve().parents[1] / ".runtime" / "official-mcp"
)).expanduser().resolve()
DEFAULT_MCP_ARGS = ("-m", "blmcp", "--transport", "stdio")


class OfficialBackendError(RuntimeError):
    pass


def runtime_python(runtime_root=None):
    root = DEFAULT_RUNTIME_ROOT if runtime_root is None else Path(runtime_root).expanduser().resolve()
    return root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


DEFAULT_MCP_COMMAND = str(runtime_python())


def resolve_launch(mcp_command=None, mcp_args=None, runtime_root=None):
    """Return (executable, argument list), preserving explicit custom settings.

    None selects the official prepared backend; an empty command deliberately
    keeps the user's existing Codex MCP configuration. A missing official runtime
    fails with setup instructions; there is no community-server fallback.
    """
    if mcp_command == "":
        return "", [] if mcp_args is None else list(mcp_args)
    expected_python = runtime_python(runtime_root)
    command = str(expected_python) if mcp_command is None else os.fspath(mcp_command)
    if not isinstance(command, str) or not command.strip():
        raise OfficialBackendError("Provide a valid MCP executable path.")
    args = list(DEFAULT_MCP_ARGS) if mcp_args is None else mcp_args
    if not isinstance(args, (list, tuple)) or not all(isinstance(arg, str) for arg in args):
        raise OfficialBackendError("MCP arguments must be a list of strings.")
    if mcp_command is None or os.path.normcase(os.path.abspath(command)) == os.path.normcase(str(expected_python)):
        root = expected_python.parents[2]
        try:
            manifest = json.loads((root / "installation.json").read_text(encoding="utf-8-sig"))
            if (not expected_python.is_file() or manifest.get("source_url") != SOURCE_URL
                    or manifest.get("revision") != SOURCE_REVISION):
                raise ValueError()
        except (OSError, ValueError, TypeError, AttributeError):
            raise OfficialBackendError(
                "Official Blender Lab MCP is not prepared at %s. Run scripts/setup-official-mcp.ps1 "
                "in the project, or select its prepared Python executable in connection settings. "
                "No changes to normal Codex CLI configuration are needed." % root
            ) from None
    return command, list(args)
