/** Host model-selection configuration and public Excel tier boot metadata. */
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-host-webserver'
import z from '@deepseek-ai/schemastery'
import { EXCEL_MODELS_BOOT_KEY, ExcelModelsSchema, resolveExcelModels, type ExcelModels } from './excel-models.ts'

/** Optional product-tier presentation over the ordinary model catalog. */
export interface Config {
  /** Whether to register /model in addition to the composer picker; defaults to true. */
  registerCommand?: boolean
  /** Excel routes supplying effort metadata; the composer hides model choices. */
  excelModels?: ExcelModels | undefined
}

/** Host configuration for public model-tier presentation. */
export const Config: z<Config> = z.object({
  registerCommand: z.boolean().default(true),
  excelModels: z.union([z.const(undefined), ExcelModelsSchema]),
})

/**
 * Supply product-tier routes and command availability before browser plugins start.
 * @param ctx - Host plugin context.
 * @param config - Validated tier presentation and command registration configuration.
 */
export function apply(ctx: Context, config: Config): void {
  const excelModels = resolveExcelModels(config.excelModels)
  ctx.on('webserver/index-inject', (table) => {
    table.push({ kind: 'global', name: '__DSH_MODEL_COMMAND__', value: config.registerCommand !== false })
    if (excelModels !== undefined) table.push({ kind: 'global', name: EXCEL_MODELS_BOOT_KEY, value: excelModels })
  })
}
