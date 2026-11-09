# Contributing

Useful contributions include reproducible bug reports, clearer setup instructions, focused fixes and platform support.

1. Read the [README](README.md), [architecture](ARCHITECTURE.md) and [development guide](docs/development.md).
2. Open an issue for a larger behavior or architecture change.
3. Create a focused branch from `main` and keep unrelated changes separate.

Describe the user-visible problem, resulting behavior and relevant validation in pull requests. Include tool versions when relevant. Distinguish simulated tests from live Blender/model/provider checks.

Run the Python suite for Python changes, browser contracts for UI changes, and Windows build/package checks for host or packaging changes. Commit regenerated web assets and notices with UI source changes. Preserve vendored hashes and upstream licenses.

Keep credentials, `.env` files, private transcripts, runtime folders, dependency caches, scenes and presentation PDFs out of commits. Redact private paths and keys from published logs and screenshots.

Contributions to original project code use GPL-3.0-or-later. Third-party files retain their stated licenses.
