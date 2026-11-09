# Blender Codex

**Chat with an AI assistant inside Blender, using your current scene as context.**

Blender Codex is an experimental Windows add-on. Ask about selected objects, request scene changes, attach a viewport image, and follow tool activity without switching applications. It uses your existing Codex sign-in and the official Blender Lab MCP integration.

Built as part of the **[Cursor x Sandbox Hackathon | Stuttgart](https://luma.com/spacexai-tueh)** on **7 November 2026**, organised by Sandbox and CREATORS.

[Deutsch](README.de.md) · [Installation](docs/getting-started.md) · [Development](docs/development.md) · [Contributing](CONTRIBUTING.md)

## Features

- Scene, object and mesh-selection context captured when you send a message.
- Scene inspection and editing through the connected Blender Lab MCP tools.
- Movable, resizable chat with streaming responses, tool activity and local history.
- Explicit viewport-image attachments, including Blender annotations.
- Optional reference-image-to-GLB generation through Hi3D with your own credentials.

Try selecting a cube and asking **“What is selected?”**, then **“Double the selected cube's height; leave X and Y unchanged.”** Check the resulting dimensions in Blender's Item panel.

## Get started

The embedded interface targets **Windows x64**. The add-on declares Blender **4.2+**; earlier local integration checks used **Blender 5.2.3 LTS**. This is a hackathon prototype; compatibility with every Blender or Codex version is not established.

You need Blender, Git, Python 3.10+, a signed-in Codex CLI and the Microsoft Edge WebView2 Runtime. Building the native host also requires the .NET Framework x64 C# compiler. Web assets are checked in; Node.js and pnpm are only needed to rebuild the interface or run browser tests.

```powershell
git clone https://github.com/david2002ochs-droid/blender-codex.git
cd blender-codex
pwsh -NoProfile -File scripts/check-prerequisites.ps1
```

Follow the **[step-by-step installation guide](docs/getting-started.md)** to prepare Blender Lab MCP, build the Windows host and install the add-on ZIP.

## How it works

```text
Blender scene + selection
        ↓
Embedded chat → local authenticated bridge → Codex App Server
                                                   ↓
                                           Blender Lab MCP
                                                   ↓
                                             Blender scene
```

The add-on supplies context and displays events. Codex owns the conversation and tool loop. Blender operations run on its main thread. See [architecture](ARCHITECTURE.md).

## Access, data and limits

The current default is **Full Access**: the Codex child process can access files, run commands and use the network without individual approvals. The permission selector also supports On Request and Read Only.

Scene context and explicitly attached images are sent to your configured Codex service. Chat history is stored locally. Hi3D is optional: generation uploads selected images to that provider and may consume paid credits. See [Hi3D setup](docs/hi3d.md).

Automated checks cover transport, context, history, provider behavior and the compiled interface with simulated responses. They do not prove a complete model-driven scene edit or paid cloud generation. See [current status](CURRENT_UI.md).

## Repository guide

| Path | Purpose |
| --- | --- |
| `blender_codex/` | Blender add-on, transport, bridge and packaged web assets |
| `frontend/src/` | React adapters for the embedded chat |
| `frontend/vendor/deepblick/` | Pinned MIT-licensed UI components and source manifest |
| `native/` | Windows WebView2 host source |
| `scripts/` | Setup, build, packaging and preview commands |
| `tests/` | Unit, browser and Blender integration checks |
| `docs/` | Installation, development and feature documentation |

## Contributing and license

Ideas, bug reports, documentation improvements and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Original project code is licensed under **GPL-3.0-or-later**; see [LICENSE](LICENSE). Third-party components retain their licenses, including the MIT-licensed Deepblick UI and Microsoft WebView2 terms. See [third-party notices and credits](THIRD_PARTY_NOTICES.md).

This is an independent community project; no official product affiliation with Blender, OpenAI or Cursor is implied.
