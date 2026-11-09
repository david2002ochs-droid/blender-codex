# Install on Windows

## 1. Prerequisites

- PowerShell 7 (`pwsh`). Run the commands below from PowerShell 7.
- Windows x64 and Blender. The add-on declares Blender 4.2+; local integration work used 5.2.3 LTS.
- Git and Python 3.10+. Blender's bundled Python can prepare the MCP runtime.
- The Codex CLI available as `codex`, with your sign-in completed.
- Microsoft Edge WebView2 Runtime.
- The .NET Framework x64 C# compiler at `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`.

From the repository root:

```powershell
pwsh -NoProfile -File scripts/check-prerequisites.ps1
```

This lists common tool paths. Check WebView2 and the compiler separately if the host build or startup reports they are missing.

## 2. Prepare Blender Lab MCP

```powershell
pwsh -NoProfile -File scripts/setup-official-mcp.ps1 -PythonPath "C:\path\to\python.exe"
```

Supply your actual Python path. For the development Blender installation it was `C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe`.

The script downloads a pinned revision of the [official Blender Lab MCP](https://projects.blender.org/lab/blender_mcp), installs dependencies in a project-local virtual environment, applies the pinned Windows stdin compatibility patch, and creates:

```text
.runtime/official-mcp/installation.json
.runtime/official-mcp/blender-lab-mcp-addon.zip
```

In Blender, open **Edit → Preferences → Add-ons → Install from Disk**. Install that official add-on ZIP and enable it. Enable its connection to the Blender instance you intend to control. Use one targeted instance.

## 3. Build and package Blender Codex

Compiled web assets are included in the checkout. Build the native host, then package:

```powershell
pwsh -NoProfile -File scripts/build-web-host.ps1
pwsh -NoProfile -File scripts/package.ps1
```

The host build downloads the pinned WebView2 SDK from NuGet and compiles the Windows host. It does not install the WebView2 Runtime. Packaging creates `dist/blender_codex.zip`, including licenses and third-party notices.

Install this ZIP through Blender's **Install from Disk** menu and enable **Codex Chat**.

## 4. Connect the installed add-on

An installed add-on needs the prepared MCP runtime. Set `BLENDER_CODEX_OFFICIAL_RUNTIME` to the **absolute** path of `.runtime/official-mcp` before launching Blender:

```powershell
$env:BLENDER_CODEX_OFFICIAL_RUNTIME = (Resolve-Path .runtime/official-mcp).Path
& "C:\path\to\blender.exe"
```

Alternatively, use the chat's connection settings to select the MCP executable printed by setup and arguments `["-m","blmcp","--transport","stdio"]`. Set the Codex executable there if it is not available on Blender's PATH.

Open the **Codex** tab in the 3D Viewport sidebar (`N`). The chat connects automatically when its executable and runtime settings are valid. Connection settings are in the chat settings dialog. Choose the desired permission mode; Full Access is the current default.

## 5. Try a scene request

Select a cube and ask “What is selected?” Then ask “Double this cube's height; leave X and Y unchanged.” Inspect its dimensions in Blender. Try Stop during an active request and the approval flow in On Request mode.

Save work before experimenting with scene edits. Viewport attachments include visible editor content and are sent only when explicitly included.

## Isolated development preview

After setup and packaging:

```powershell
pwsh -NoProfile -File scripts/start-preview.ps1 -BlenderPath "C:\path\to\blender.exe" -CodexPath "C:\path\to\codex.exe"
```

The launcher extracts a package into a fresh local runtime directory and writes a startup receipt. It does not install the add-on into your normal Blender profile.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Native host build fails | Windows x64, .NET compiler, access to NuGet |
| Chat is blank | Installed WebView2 Runtime and packaged native host files |
| Codex cannot start | Run the same executable from a terminal and complete sign-in |
| MCP runtime cannot be found | Absolute runtime environment variable or explicit executable settings |
| Connected but scene tools fail | Official add-on enabled, correct Blender instance and matching MCP connection |
| Behavior changes after a Codex upgrade | Re-run local checks; the App Server protocol is version-dependent |

Hi3D credentials are optional and separate from chat setup. See [Hi3D](hi3d.md).
