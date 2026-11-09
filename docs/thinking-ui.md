# Public Thinking summaries in the existing Deepblick UI

The adapter renders optional public reasoning summaries using the pinned Deepblick UI components. Vendored source remains byte-identical to the revision in `frontend/vendor/deepblick/SOURCE.json`; the build verifies its hashes.

## Actual supported protocol

Development compatibility reference: locally generated `protocol/codex_app_server_protocol.v2.schemas.json`, SHA256 `f2576ca5d46be4cfb159906264fbc173efcfcc917ea8fdc38323770e7b657b5a`. This identifies the inspected schema bytes, not an assertion about an unverified installed CLI version.

| App Server surface | Adapter behavior |
| --- | --- |
| `turn/start.summary = "auto"` (`TurnStartParams`) | Requests an optional public summary; does not promise that a model supplies one. |
| `item/started`, `item.type = "reasoning"` | Creates one live row using real threadId, turnId, item.id; only `summary: string[]` is accepted. |
| `item/reasoning/summaryPartAdded` | Creates the specified `summaryIndex` without clearing already streamed text. |
| `item/reasoning/summaryTextDelta` | Appends `delta` to its specified `summaryIndex`; index order determines paragraph order. |
| `item/completed`, reasoning item | Replaces streamed parts with a nonempty authoritative `summary` under the same identity. Empty summaries preserve already received public text. |
| `turn/completed` | Reconciles any included reasoning items, then records completed/failed/interrupted. Optional `startedAt`, `completedAt`, `durationMs` are copied; no estimated timing. |
| `thread/turns/list`, `itemsView = "full"` | Hydrates reasoning from original item order and IDs. Replaces the provisional cache; public cached text is retained only for the same real item when the server supplies no summary. |
| Fatal/rejected transport error, disconnect | Stops running rows as failed/interrupted; an already settled earlier turn retains its outcome. Retry notifications do not falsely stop a continuing turn. |

`item/reasoning/textDelta`, reasoning `content`, `encryptedContent`, and plan text are **not** summary sources. They are neither rendered nor reconstructed. Plan events are not mislabeled as tools or thinking. There is no fallback generated reasoning text. The schema's summary-delta notification contains no event sequence/id for deduplicating identical individual retransmitted delta packets; the adapter therefore does not discard repeated strings, which can be legitimate. Lifecycle and history duplicates are reconciled by `(thread_id, turn_id, item_id)`; late starts/deltas cannot reopen completed rows, and completed-turn notifications are rejected by the client.

## Original rendering and bounded projection

The frontend translates each bounded summary into the original `assistant-step` reasoning block. `AssistantNodeView` → `AssistantMarkdown` → `ReasoningRow` retains original Markdown, CSS, disclosure, live paragraph preview, shimmer and accessibility. The latest Blender UI's unfolded work details now use Deepblick's actual **verbose** presentation policy instead of unused ad-hoc `reasoning: expanded` properties. Individual Think disclosures remain initially collapsed, exactly as the original component specifies, and keep their user-selected state during updates. The existing `DeepblickThinkingEye` remains the real running indicator, including when no summary exists. A settled blank summary disappears according to the original component.

One original `TurnProcessNodeView` per retained reasoning turn shows Completed/Failed/Stopped. Whole-turn folding stays disabled under the preserved verbose policy; the individual Think row still folds. The original duration formatting is used only when actual start plus duration/end are available. Token/size/percentage estimates are not invented. Synthetic UI control keys are explicit `turn-process:[thread,turn]` keys, not fake durable server item IDs; the control's fractional ordering offset is presentation-only.

Limits: at most **32 summary parts**, **16,384 characters per item**, **131,072 characters across retained summary text**, and **64 retained rows**. Client events are bounded before queueing, state applies the same limits to streaming, completed items and history, and private part buffers are released on completion. The wire/history projection stores only the bounded public text once. The UI reports clipped previews and omitted older rows separately from the summary text. These are local previews; the upstream App Server history is not rewritten. Existing `bounded_state` remains the final 4 MiB transport guard. No additional full-summary resource is created, preventing repeated streaming snapshots from exhausting the resource store. Node sources no longer accumulate after transcript entries disappear.

## Verification and delivery

`tests/test_reasoning.py`: official-schema shape checks, public summary configuration, indexed streaming, final readback, lifecycle deduplication, wrong thread/turn isolation, raw-reasoning exclusion, failure/interruption/disconnect, persisted cache and canonical history, empty summaries, huge Unicode payloads and history payloads. It exports deterministic replay snapshots through the actual client and state classes.

`tests/test_thinking_frontend.cjs`: serves the actual compiled `blender_codex/web` bundle and consumes those snapshots. Tests original disclosure behavior, streaming preview, completion timing, failed/interrupted/history, absence of fabricated duration, empty-summary hiding, large-preview notices and reduced motion. Screenshots deliberately contain fixture text and do not claim a live model turn. Existing Deepblick and image-annotation production-browser contracts are also rerun.

Run the unit and browser commands in [development.md](development.md). Local generated schemas are optional and are excluded from Git. Browser screenshots contain explicit test fixtures; they are not evidence of a live model turn or an independent comparison with another installed application.
