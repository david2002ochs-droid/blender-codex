/** Product effort choices over explicit deployment routes and Host capabilities. */
import type { ModelSelection } from '@deepseek-ai/dsh-api-remotes/client'
import type { ExcelModels } from '../excel-models.ts'
import type { ModelDirectoryState } from './directory.ts'

/** One product level and its complete selection; missing metadata keeps the row visible but unavailable. */
export interface ExcelEffortChoice {
  key: 'base' | 'medium' | 'high' | 'xhigh' | 'max'
  selection: ModelSelection
  available: boolean
}

/**
 * Compare the complete route and effort without applying provider defaults.
 * @param a - Saved selection.
 * @param b - Offered selection.
 * @returns Whether both target the same route and effort.
 */
export function sameSelection(a: ModelSelection | null, b: ModelSelection): boolean {
  return a?.provider === b.provider && a.model === b.model && a.reasoningEffort === b.reasoningEffort
}

/**
 * Resolve the five product levels without inferring provider capabilities.
 * @param config - Explicit deployment routes and product policy.
 * @param groups - Host-advertised exact-model reasoning capabilities.
 * @returns Product choices, or undefined for an ordinary/legacy deployment.
 */
export function excelEfforts(config: ExcelModels | undefined, groups: ModelDirectoryState['groups']): ExcelEffortChoice[] | undefined {
  if (config?.effortPolicy === undefined || config.pro === undefined) return undefined
  return ([['base', config.flash, 'low'],
    ['medium', config.flash, 'medium'], ['high', config.flash, 'high'], ['xhigh', config.pro, 'medium'], ['max', config.pro, 'high']] as const).map(([key, route, reasoningEffort]) => ({
    key, selection: { ...route, reasoningEffort },
    available: groups.find(group => group.id === route.provider)?.models.find(model => model.id === route.model)
      ?.reasoning?.efforts.some(effort => effort.id === reasoningEffort) === true,
  }))
}

/**
 * Decide whether a nonblank chat needs cost acknowledgement before changing selection.
 * @param previous - Authoritative current selection.
 * @param next - Requested complete selection.
 * @param cacheFriendlyChanges - Explicit qualification for effort-only changes on the deployed routes.
 * @returns Whether cache advantages may be lost and the user must confirm.
 */
export function needsEffortConfirmation(previous: ModelSelection | null, next: ModelSelection, cacheFriendlyChanges: boolean): boolean {
  return previous !== null && !sameSelection(previous, next)
    && (previous.provider !== next.provider || previous.model !== next.model || !cacheFriendlyChanges)
}
