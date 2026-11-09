# Development

The Python add-on runs inside Blender. Transport, state and provider tests also run with ordinary Python and the standard library. Native embedding requires Windows. Browser tests load the compiled interface with simulated backend data.

## Python tests

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Optional pinned-MCP tests require `.runtime/official-mcp/source/`, prepared by setup. Schema compatibility checks require a locally generated Codex App Server schema at `protocol/codex_app_server_protocol.v2.schemas.json`. Optional checks report skips when their local resources are absent. The normal suite runs from a fresh checkout without credentials, Blender or a live model/provider call.

## Rebuild the chat

Use Node.js 24 and the pnpm version recorded in `frontend/package.json`:

```powershell
cd frontend
pnpm install --ignore-scripts --frozen-lockfile
pnpm build
cd ..
```

The build verifies pinned upstream file hashes, then regenerates web assets, notices and build metadata. Commit generated runtime assets with UI source changes. Avoid manually patching generated `app.js` or vendored files.

## Browser tests

```powershell
cd tests/browser
pnpm install --ignore-scripts --frozen-lockfile
pnpm exec playwright install chromium
cd ../..
node tests/run-browser-tests.cjs
```

The runner checks the Deepblick chat, image annotation, public summary and Blender hero contracts. It creates summary replay data through the actual Python client/state test. Set `PYTHON` if your interpreter is not `python`. Optional `PLAYWRIGHT_MODULE` and `CHROME_PATH` can reuse installed tools. Screenshots and receipts go under ignored `.runtime/`.

## Windows package

```powershell
pwsh -NoProfile -File scripts/build-web-host.ps1
pwsh -NoProfile -File scripts/package.ps1
python tests/integration_package.py --output .runtime/package-check.json
python tests/integration_package_checks.py
```

The inspector compares package bytes with sources, verifies local asset references and rejects development files. Packaging includes the project license and third-party notices. Built executables, DLLs and ZIPs stay out of Git.

## Blender checks

```powershell
blender --background --factory-startup --python tests/smoke_blender.py
blender --background --factory-startup --python tests/smoke_hi3d_blender.py
```

Other `smoke_*.py` and `integration_*.py` scripts cover connection/lifecycle scenarios. Read their docstrings before running: some require the official runtime or a configured Codex executable. Offline unit/browser/package checks do not start paid provider jobs.

See [architecture](../ARCHITECTURE.md), [frontend notes](../frontend/README.md) and [contribution guide](../CONTRIBUTING.md).
