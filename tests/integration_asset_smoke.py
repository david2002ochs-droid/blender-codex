"""Serve the built UI through the actual bridge, checking assets and resources.

Only an isolated loopback listener and temporary resource bytes are used.
No Blender/Codex/model/provider process is started. A source change invalidates
the receipt. Token values and token-bearing launch URLs are never recorded.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urljoin

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hashes():
    paths = [ROOT / "blender_codex/web_bridge.py", ROOT / "blender_codex/session_state.py"]
    paths += [path for path in (ROOT / "blender_codex/web").rglob("*") if path.is_file()]
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime/deepblick-assets-receipt.json")
    args = parser.parse_args()
    before = hashes()
    bridge_module = load("actual_asset_bridge", ROOT / "blender_codex/web_bridge.py")
    inspector = load("actual_asset_inspector", ROOT / "tests/integration_package.py")
    bridge = bridge_module.WebBridge()
    results, failures = [], []
    try:
        url = urlsplit(bridge.start())
        origin = "%s://%s" % (url.scheme, url.netloc)

        def get(path, token=False):
            request = urllib.request.Request(origin + path, headers={"X-Codex-Token": bridge.token} if token else {})
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return response.status, response.read(), response.headers.get("Content-Type", ""), response.headers.get("Content-Security-Policy", "")
            except urllib.error.HTTPError as error:
                return error.code, error.read(), "", ""

        status, html, _mime, csp = get("/")
        results.append({"path": "/", "status": status, "bytes": len(html)})
        if status != 200:
            failures.append("UI entry HTML is not served")
        references = inspector.HTMLReferences()
        references.feed(html.decode("utf-8"))
        for reference in references.references:
            path = urlsplit(urljoin(origin + "/", reference)).path
            status, body, mime, _ = get(path)
            results.append({"path": path, "status": status, "bytes": len(body), "mime": mime})
            if status != 200:
                failures.append("Required UI asset unavailable: " + path)
        for required in ("style-src 'self' 'unsafe-inline'", "img-src 'self' blob: data:", "font-src 'self' data:"):
            if required not in csp:
                failures.append("Required production component CSP directive missing: " + required)
        descriptor = bridge.resources.add("fixture.txt", "text/plain", b"resource-smoke-fixture", upload=True)
        resource_path = descriptor["resource_url"]
        status, body, _mime, _ = get(resource_path, token=True)
        if status != 200 or body != b"resource-smoke-fixture":
            failures.append("Authenticated resource did not return registered bytes")
        unauthorized, _body, _mime, _ = get(resource_path)
        if unauthorized != 401:
            failures.append("Resource was not protected by session token")
        results.append({"path": "/api/resources/<fixture-handle>", "authenticated_status": status,
                        "unauthenticated_status": unauthorized})
    finally:
        bridge.stop()
        bridge.resources.close()
    after = hashes()
    stable = before == after
    receipt = {"passed": not failures and stable, "stable_snapshot": stable, "checks": results,
               "failures": failures, "sha256_before": before, "sha256_after": after,
               "scope": "actual bridge and built assets; local fixture resource only; no model call"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("ACTUAL_BRIDGE_ASSET_SMOKE", "PASS" if receipt["passed"] else "FAIL", "stable=" + str(stable))
    for failure in failures:
        print("FAIL", failure)
    return 2 if not stable else 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
