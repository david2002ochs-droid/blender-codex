# Current status

Public source snapshot prepared on 9 November 2026 from the reviewed 7 November hackathon candidate. This is an experimental Windows x64 integration.

## Included

- Pinned Deepblick chat components and Blender-specific welcome screen.
- Movable/resizable WebView2 host and automatic connection recovery.
- Streaming, tool activity, permission controls and local chat history.
- Bounded public reasoning summaries and large JSONL history handling.
- Explicit viewport attachment and Blender annotations.
- Optional Hi3D single-image and multi-view generation adapter.

## Limits

- Linux and macOS embedding are not implemented.
- In-flight steering is unfinished and not included.
- Image annotation controls depend on backend capabilities; browser fixtures do not prove their availability in a live session.
- Public reasoning summaries depend on what the configured model supplies.
- Unit/browser tests use simulated responses. They do not establish a completed model-driven scene edit, paid generation, native download behavior or independent pixel parity with another application.
- Earlier Blender startup checks reached Connected. A connection alone is not an end-to-end acceptance result.

Run [the development checks](docs/development.md) against your installed versions. Public CI results are available in the repository's Actions tab.
