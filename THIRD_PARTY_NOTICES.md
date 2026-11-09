# Third-party notices and credits

Original Blender Codex code is licensed under **GPL-3.0-or-later**, with the text in [LICENSE](LICENSE). Third-party notices and licenses take precedence for the files they cover.

## Project contributors

The prototype and reviewed integration were developed by contributors to `leonielautsch/blender_agent`, including **leonielautsch** and **david2002ochs-droid**. This repository publishes fresh source history from reviewed candidate `45d37b0d23ceff64e3a27c7ebe7386174057bd2c`, excluding private development logs and repository history.

## Deepblick UI

Vendored components come from `david2002ochs-droid/deepseek-excel-harness`, commit `2f3f5d304d0bd3ccc9f866dab4799d501d3d2c65`. The MIT copyright notice identifies DeepSeek. Attribution does not imply endorsement of this Blender adapter.

- [Source manifest](frontend/vendor/deepblick/SOURCE.json)
- [MIT license](frontend/vendor/deepblick/LICENSE)
- [Packaged UI license](blender_codex/web/DEEPBLICK-LICENSE.txt)
- [Bundled dependency, font and icon notices](blender_codex/web/THIRD-PARTY-NOTICES.txt)

The frontend build regenerates dependency notices. Fonts, icons and nested utilities retain their included licenses.

## Microsoft WebView2

SDK components are downloaded from NuGet at build time. Their terms remain in [WebView2-LICENSE.txt](blender_codex/native/WebView2-LICENSE.txt) and accompany packaged native files. The project's GPL license does not replace Microsoft's component terms.

## Blender Lab MCP

The official [Blender Lab MCP](https://projects.blender.org/lab/blender_mcp) is a separate GPL-3.0-or-later dependency. Setup pins its revision and creates a separate official add-on ZIP with its license. Runtime source checkouts are excluded from this repository. The stdin compatibility patch is under `patches/`.

## Hackathon

Developed as part of the **Cursor x Sandbox Hackathon | Stuttgart**, **7 November 2026**, organised by **Sandbox and CREATORS**. [Official event page](https://luma.com/spacexai-tueh); [dated listing](https://brainberg.eu/events/cursor-x-sandbox-hackathon-or-stuttgart-2026-11-07-stuttgart).
