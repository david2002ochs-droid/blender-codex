/** Host registration for browser Chat preferences. */
import type {} from '@deepseek-ai/dsh-settings'
import type {} from '@deepseek-ai/dsh-host-webserver'

import type { Volatile, Context } from '@deepseek-ai/cordis'
import type { ChatSettings, LinkOpening, PerformanceUsageMode } from './chat-settings.ts'
import z from '@deepseek-ai/schemastery'
import { TRANSCRIPT_VIEW_FIELD } from './chat-settings.ts'

import { ChatSettingsFields } from './chat-settings.ts'

export {
  CHAT_SETTINGS_NAMESPACE, DEFAULT_TRANSCRIPT_VIEW_MODE, LEGACY_TRANSCRIPT_VIEW_MODE,
  LEGACY_EXPANDED_TRANSCRIPT_VIEW_MODE, TRANSCRIPT_VIEW_FIELD,
  TRANSCRIPT_VIEW_MODES, type ChatSettings, type TranscriptViewMode,
} from './chat-settings.ts'

/** Runtime preferences projected to the browser. */
export interface Config {
  /** Expose conversation branching controls in this deployment. */
  allowBranching: boolean
  /** Show the activity and usage statistics pills in the composer dock. */
  showComposerStats: boolean
  /** Show completed-turn token usage actions in this deployment. */
  showTurnUsage: boolean
  /** Completed turn transcript presentation. */
  transcriptView: Volatile<ChatSettings['transcriptView']>
  /** Performance and usage detail level. */
  performanceUsage: Volatile<PerformanceUsageMode>
  /** Default destination for Chat HTTP(S) links. */
  linkOpening: Volatile<LinkOpening>
}

/** Live preferences projected to the browser. */
export const Config = z.object({
  allowBranching: z.boolean().default(true),
  showComposerStats: z.boolean().default(true),
  showTurnUsage: z.boolean().default(true),
  transcriptView: ChatSettingsFields[TRANSCRIPT_VIEW_FIELD].volatile(),
  performanceUsage: ChatSettingsFields['performanceUsage'].volatile(),
  linkOpening: ChatSettingsFields.linkOpening.volatile(),
})

/** Host preferences are consumed through the configuration form projection.
 * @param ctx Plugin context used for optional settings presentation.
 * @param config Validated deployment controls and live preferences.
 */
export function apply(ctx: Context, config: Config): void {
  ctx.on('webserver/index-inject', (table) => {
    table.push({ kind: 'global', name: '__DSH_ALLOW_BRANCHING__', value: config.allowBranching })
    table.push({ kind: 'global', name: '__DSH_SHOW_COMPOSER_STATS__', value: config.showComposerStats })
    table.push({ kind: 'global', name: '__DSH_SHOW_TURN_USAGE__', value: config.showTurnUsage })
  })
  ctx.inject(['settings'], (child) => { child.effect(() => child.settings.configure({ auto: false }, ctx.fiber)) })
}
