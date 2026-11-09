"""Read local Hi3D credentials without exporting them to os.environ or bpy.

Supported .env subset: KEY=value, optional matching quotes, comment lines and
trailing comments. Values are literal: no expansion, escapes or shell execution.
Only the two Hi3D credential names are read; error messages never echo values.
"""
import os
from pathlib import Path
import re

NAMES = ("HI3D_CLIENT_ID", "HI3D_CLIENT_SECRET")
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _pair(values):
    pair = tuple(str(value or "").strip() for value in values)
    if len(pair) != 2 or (any(pair) and not all(pair)):
        raise ValueError("Set both HI3D_CLIENT_ID (AK) and HI3D_CLIENT_SECRET (SK) in the same credential source.")
    if any(any(c in value for c in "\r\n\x00") for value in pair):
        raise ValueError("Hi3D credentials must be single-line values.")
    return pair


def _read_env(path):
    try:
        with Path(path).open("rb") as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError()
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeError, ValueError):
        raise ValueError("Cannot read the Hi3D .env file; use UTF-8 text below 64 KiB.") from None
    values = {}
    for line in text.splitlines():
        match = re.match(r"^\s*(?:export\s+)?(HI3D_CLIENT_ID|HI3D_CLIENT_SECRET)\s*=(.*)$", line)
        if not match:
            continue
        key, value = match.groups()
        if key in values:
            raise ValueError("A Hi3D credential is defined more than once in .env.")
        value = value.strip()
        if value.startswith(("'", '"')):
            end = value.find(value[0], 1)
            if end < 0 or (value[end + 1:].strip() and not value[end + 1:].strip().startswith("#")):
                raise ValueError("Invalid quotes in the Hi3D .env file.")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[key] = value
    return _pair(values.get(name, "") for name in NAMES)


def load_credentials(*, explicit=None, cwd=None, env_file=None, environ=None):
    """Priority: explicit pair, process pair, selected .env, project/source .env.

    Never combine AK from one source with SK from another. Explicit empty pairs
    disable fallback, which also keeps offline tests independent of real keys.
    """
    if explicit is not None:
        return _pair(explicit)
    environment = os.environ if environ is None else environ
    pair = _pair(environment.get(name, "") for name in NAMES)
    if any(pair):
        return pair
    selected = env_file or environment.get("HI3D_ENV_FILE")
    if selected:
        path = Path(selected).expanduser()
        if not path.is_absolute():
            path = Path(cwd or Path.cwd()) / path
        return _read_env(path)
    candidates = [Path(cwd or Path.cwd()) / ".env", SOURCE_ROOT / ".env"]
    for path in dict.fromkeys(candidates):
        if path.is_file():
            return _read_env(path)
    return ("", "")
