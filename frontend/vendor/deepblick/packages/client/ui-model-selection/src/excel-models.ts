/** Deployment-selected Excel routes supplying effort metadata. */
import z from '@deepseek-ai/schemastery'

/** Public boot property carrying only model identifiers. */
export const EXCEL_MODELS_BOOT_KEY = '__DSH_EXCEL_MODELS__'

/** Provider and model selected by one product tier. */
export interface ExcelModelRoute {
  /** Provider registry identifier for the configured route. */
  provider: string
  /** Model identifier within the configured provider. */
  model: string
}

/** Explicit Excel route and an optional second route for deployments that expose two tiers. */
export interface ExcelModels {
  /** Primary Excel route. */
  flash: ExcelModelRoute
  /** Optional retained route metadata; this route is not offered by the product picker. */
  luna?: ExcelModelRoute | undefined
  /** Optional additional route for two-tier deployments. */
  pro?: ExcelModelRoute | undefined
  /** Five effort levels across the primary and additional routes; account authorization remains the product default. */
  effortPolicy?: {
    /** openai requires account rights; openai-direct-developer uses only real Host capabilities for private direct routes. */
    kind: 'openai' | 'openai-direct-developer'
    /** Whether every deployed route is qualified to preserve its prefix across effort-only changes. */
    cacheFriendlyChanges: boolean
  } | undefined
}

const RouteSchema = z.object({ provider: z.string().required(), model: z.string().required() })

/** Validate optional Host or index-injected tier configuration. */
export const ExcelModelsSchema: z<ExcelModels> = z.object({
  flash: RouteSchema.required(),
  pro: z.union([z.const(undefined), RouteSchema]),
  luna: z.union([z.const(undefined), RouteSchema]),
  effortPolicy: z.union([z.const(undefined), z.object({
    kind: z.union([z.const('openai'), z.const('openai-direct-developer')]).required(), cacheFriendlyChanges: z.boolean().required(),
  })]),
})

/**
 * Validate the optional tier configuration at the browser boot input.
 * @param value - Host-injected public configuration.
 * @returns Configured routes, or undefined for the ordinary model catalog.
 */
export function resolveExcelModels(value: unknown): ExcelModels | undefined {
  if (value === undefined) return undefined
  const route = (candidate: unknown): candidate is ExcelModelRoute => typeof candidate === 'object'
    && candidate !== null && 'provider' in candidate && typeof candidate.provider === 'string'
    && candidate.provider.trim() !== '' && 'model' in candidate && typeof candidate.model === 'string'
    && candidate.model.trim() !== ''
  if (typeof value !== 'object' || value === null || !('flash' in value) || !route(value.flash)) {
    throw new Error('excelModels requires an explicit Flash provider/model route')
  }
  const pro = 'pro' in value ? value.pro : undefined
  if (pro !== undefined && !route(pro)) throw new Error('excelModels requires valid provider/model routes')
  if (pro !== undefined && value.flash.provider === pro.provider && value.flash.model === pro.model) {
    throw new Error('excelModels requires distinct Flash and Pro routes')
  }
  const luna = 'luna' in value ? value.luna : undefined
  if (luna !== undefined && !route(luna)) throw new Error('excelModels requires a valid Luna route')
  const effortPolicy = 'effortPolicy' in value ? value.effortPolicy : undefined
  if (luna !== undefined && [value.flash, pro].some(other => other !== undefined
    && other.provider === luna.provider && other.model === luna.model)) throw new Error('excelModels requires distinct product routes')
  if (effortPolicy !== undefined && pro === undefined) throw new Error('excelModels effortPolicy requires both routes')
  let policy: ExcelModels['effortPolicy']
  if (effortPolicy !== undefined) {
    if (typeof effortPolicy !== 'object' || effortPolicy === null || !('kind' in effortPolicy)
      || effortPolicy.kind !== 'openai' && effortPolicy.kind !== 'openai-direct-developer'
      || !('cacheFriendlyChanges' in effortPolicy) || typeof effortPolicy.cacheFriendlyChanges !== 'boolean') {
      throw new Error('excelModels effortPolicy requires a supported kind and explicit cache qualification')
    }
    policy = { kind: effortPolicy.kind, cacheFriendlyChanges: effortPolicy.cacheFriendlyChanges }
  }
  return ExcelModelsSchema({ flash: value.flash, ...(luna === undefined ? {} : { luna }), ...(pro === undefined ? {} : { pro }),
    ...(policy === undefined ? {} : { effortPolicy: policy }) })
}
