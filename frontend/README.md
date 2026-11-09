# Deepblick production views in Blender

This Blender-owned Codex adapter imports unchanged production components from
`vendor/deepblick`, not `scripts/ui-review` and not a CSS imitation. There is no
second Harness RPC connection, provider runtime or agent loop.

Source: `david2002ochs-droid/deepseek-excel-harness`, commit
`2f3f5d304d0bd3ccc9f866dab4799d501d3d2c65`, MIT license.
`vendor/deepblick/SOURCE.json` records each source file and SHA256, verified on
every build. The extra schema/brand/retention utilities are view dependencies.

## Standalone build

From this directory:

```powershell
pnpm install --ignore-scripts --frozen-lockfile
pnpm build
```

Or run `pwsh -File scripts/build-chat-ui.ps1` from the project root after
installing the dependencies. Node 24 and pnpm 11 were used for validation.
Exact direct versions plus `pnpm-lock.yaml` remove the sibling-checkout
prerequisite. Optional `--dependency-root` / `-DependencyRoot` only reuses an
already installed npm dependency cache read-only and is not required.

Output is the three assets in `blender_codex/web/` plus license notices. Blender
needs no CDN or npm server. `BUILD.json` records package versions;
`build-meta.json` records actual bundled inputs. Output is minified/tree-shaken.
The simple-icons ESM entry preserves named-export tree shaking without removing
production functionality. Build scripts never call a model or alter Codex,
credentials, provider jobs or Blender scenes.

## Actual component seams

| Adapter | Original production components |
| --- | --- |
| `project.tsx` | ChatView, MessageItem/AssistantNodeView, ToolCallTree/GenericToolCard, MessageImages |
| `composer.tsx` | InputBar, DraftEditorRuntime/Lexical, ComposerAttachments, ModelSelect, PermissionSelect |
| `conversation.tsx` | ConversationContent, ConversationSession/DefaultConversationViews, HeroShell, DeepblickHero, WorkspacePickFlow |
| `shell.tsx` | AppFrame, SidebarRoot, HeaderLeadingControls, WorkspaceBrowser, session header and Rename dialog |
| `approval.tsx` | ApprovalPanel with populated form/question details using original input atoms |
| `main.tsx` | Deepblick brand/theme, Modal, CodeBlock, gallery/lightbox; Blender layout only |

`bridge.ts` adapts authenticated state/actions/resources. Backend message/tool
IDs remain stable keys. Draft attachment IDs are browser-local and map to actual
backend handles at submission. No tool topology or durable Harness log is
invented. Plugin-only history uses actual open/new/rename actions. Backend project
paths serve only as view-local identities for the current Blender project chip;
they are not remote Harness workspace IDs. Model/policy controls appear only with real backend
capabilities/catalogs and invoke actual selection actions.

Settings paths live in the deliberately opened settings modal. Hi3D is separate;
the normal chat requests no API key. Image/text bytes use `X-Codex-Token` and
authorized blob loaders. Office/PDF conversion is absent: the preview explicitly
offers download rather than a fabricated renderer. Native downloads additionally
depend on the WebView host's policy.

`#token=…` loads the chat. There is no permanent left icon rail or upper comment
toolbar. Header controls open the actual history sidebar on demand. Plus → Zeichnen
starts temporary Blender annotation; Escape cancels it without clearing the chat
draft. View inclusion is explicit in the same chat draft. The legacy markup surface
renders nothing. No development-feedback capture is mounted.

`#token=…&surface=image-editor` is the separate contextual image editor. It requires
the actual `image_markup` backend nonce/resources capability. Opening/committing
does not start a model turn; server-admitted originals and annotated copies enter
the real composer. Multi-pane independent commit behavior remains a backend
contract issue until keep-open/batch semantics are provided.

Image generation uses actual tool events for running/completed/failed/interrupted
status. CSS motion is indeterminate and removed for reduced-motion. No development concept artwork or fixture transcript is shipped as a runtime result.

## Verification

`tests/test_deepblick_frontend.cjs` tests the production bundle against a local
authenticated fixture server. Set `PLAYWRIGHT_MODULE` and optionally
`CHROME_PATH` to installed tools. It checks Lexical, streaming, multiple tool
cards/input/result/error, stop, separate drafts, view consent, denied approval,
populated forms, authenticated images/text and unsupported document fallback.
Browser checks do not establish live Codex scene changes or native downloads;
those require Blender integration tests.


See [the development guide](../docs/development.md) for a reproducible browser-test setup.
