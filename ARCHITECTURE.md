# Architecture

Blender Codex connects a local embedded chat to Codex App Server and the official Blender Lab MCP. The add-on owns Blender context and UI projection; Codex owns model execution, conversation history and its tool loop.

```text
React chat (local assets)
    ↕ token-authenticated loopback HTTP
web_bridge.py → main-thread queue → web_ui.py / __init__.py
    ↕
codex_client.py → codex app-server (JSONL over stdio)
    ↕
Blender Lab MCP → official Blender add-on → open scene

Optional image_to_3d → bounded worker process → Hi3D HTTPS API
```

## Interface and bridge

`native/WebHost.cs` hosts WebView2 in Blender's Windows window. `web_host.py` manages that process. The chat can move and resize.

`frontend/src/` adapts pinned MIT-licensed Deepblick components to Blender. `frontend/vendor/deepblick/SOURCE.json` records upstream file hashes; the build verifies those bytes before writing `blender_codex/web/`. Packaged assets use no runtime CDN.

`web_bridge.py` binds to loopback on a random port and requires a session token. Host/origin validation, bounded requests and resource handles define the local API boundary. Server threads queue actions; `web_ui.py` performs Blender operations on its main thread.

## Context and conversation

`context.py` captures the active file, scene, frame, mode, object, selection and transformations before submission. Mesh indices are bounded and truncation is reported. Scene names are data. Viewport images are captured only with explicit inclusion.

`codex_client.py` handles streaming, tool events, approvals, cancellation, public reasoning summaries and history hydration. It launches a separate App Server with plugin-scoped configuration and the existing Codex sign-in. Full Access is the current default; On Request and Read Only map to supported server policies.

`chat_history.py` persists plugin-owned metadata locally. `session_state.py` and `state_projection.py` create bounded display projections. Thread resume uses its real server identity; UI history is not substituted for the server's conversation.

`scene_lifecycle.py`, `blender_target.py` and `auto_connect.py` manage connection recovery and instance boundaries. Only one deliberately targeted Blender instance is supported. Unsaved scene data comes from that live instance.

## Scene tools and provider

The official MCP revision is pinned in `scripts/setup-official-mcp.ps1`. Setup prepares `.runtime/official-mcp/` and applies the Windows stdin patch only to an installed helper matching known hashes. Its upstream checkout remains unchanged.

Live tools operate in the connected Blender instance. CLI tools may launch separate background Blender processes; changes there do not directly change the visible scene. `blender_codex/instructions.txt` describes the intended workflow.

`hi3d_config.py` reads complete credential pairs without interpolation or shell execution. Keys stay outside model context and job journals. `hi3d_tool.py` exposes `image_to_3d`; `native_tools.py` runs it in a bounded worker. Known task IDs resume polling without resubmission. Local Stop does not cancel a remote job. Importing a downloaded GLB is a separate scene operation.

## Verification

Unit tests use simulated transports/providers. Browser checks load the compiled UI with explicit fixtures. Blender checks cover registration, context, lifecycle and imports. Full model-driven scene editing and paid generation require live acceptance checks. See [development](docs/development.md) and [status](CURRENT_UI.md).
