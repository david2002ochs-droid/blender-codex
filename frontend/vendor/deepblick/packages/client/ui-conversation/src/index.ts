/** Host registration for browser conversation preferences. */
import type {} from '@deepseek-ai/dsh-settings'
import type {} from '@deepseek-ai/dsh-host-webserver'

import type { Volatile, Context } from '@deepseek-ai/cordis'
import type { BusyEnterBehavior } from './submission-settings.ts'
import z from '@deepseek-ai/schemastery'
import { BUSY_ENTER_FIELD } from './submission-settings.ts'

import { ConversationSettingsFields } from './submission-settings.ts'
import {
  ExcelContextConfigSchema, excelContextBootInjection, type ExcelContextConfig,
} from './excel-config.ts'
import { SHOW_CONTEXT_METER_BOOT_KEY } from './composer-config.ts'

export {
  BUSY_ENTER_BEHAVIORS, BUSY_ENTER_FIELD, CONVERSATION_SETTINGS_NAMESPACE,
  DEFAULT_BUSY_ENTER_BEHAVIOR, type BusyEnterBehavior, type ConversationSettings,
} from './submission-settings.ts'

/** Runtime preferences projected to the browser. */
export interface Config {
  /** Enter key behavior while a turn is running. */
  busyEnter: Volatile<BusyEnterBehavior>
  /** Public opt-in supplied to the browser before its plugins start. */
  excelContext?: ExcelContextConfig | undefined
  /** Use Excel-specific composer placeholders. */
  excelPresentation?: boolean | undefined
  /** Show the context-window usage meter in the composer dock. */
  showContextMeter: boolean
}

/** Live preferences projected to the browser. */
export const Config = z.object({
  busyEnter: ConversationSettingsFields[BUSY_ENTER_FIELD].volatile(),
  excelContext: z.union([z.const(undefined), ExcelContextConfigSchema]),
  excelPresentation: z.union([z.const(undefined), z.boolean()]),
  showContextMeter: z.boolean().default(true),
})

/** Host preferences are consumed through the configuration form projection.
 * @param ctx Plugin context used for optional settings presentation.
 * @param config Validated Host preferences and Excel deployment configuration.
 */
export function apply(ctx: Context, config: Config): void {
  const boot = excelContextBootInjection(config.excelContext)
  ctx.inject(['settings'], (child) => { child.effect(() => child.settings.configure({ auto: false }, ctx.fiber)) })
  ctx.on('webserver/index-inject', (table) => {
    if (boot !== undefined) table.push(boot)
    if (config.excelPresentation === true) table.push({ kind: 'global', name: '__DSH_EXCEL_PRESENTATION__', value: true })
    table.push({ kind: 'global', name: SHOW_CONTEXT_METER_BOOT_KEY, value: config.showContextMeter })
  })
}
