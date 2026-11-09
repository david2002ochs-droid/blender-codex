/** Localized product tiers over the Host's advisory model metadata. */
import type { TranslateNS } from '@deepseek-ai/dsh-client-ui-slots'
import type { ExcelModels } from '../excel-models.ts'
import type { ModelDirectoryState } from './directory.ts'

/**
 * Limit Excel presentation to its configured routes and retain capability metadata.
 * @param groups - Host model catalog groups.
 * @param routes - Optional Flash and Pro routes.
 * @param t - Model namespace translator.
 * @returns Ordinary groups or the localized Excel tier groups.
 */
export function excelModelGroups(
  groups: ModelDirectoryState['groups'], routes: ExcelModels | undefined, t: TranslateNS<'model'>,
): ModelDirectoryState['groups'] {
  if (routes === undefined) return groups
  return groups.map(group => ({
    ...group,
    name: t('menu.model'),
    models: group.models.flatMap((model) => {
      const tier = routes.flash.provider === group.id && routes.flash.model === model.id ? 'flash'
        : routes.pro?.provider === group.id && routes.pro.model === model.id ? 'pro' : undefined
      return tier === undefined ? [] : [{ ...model, name: t(tier === 'flash' ? 'tier.flash' : 'tier.pro') }]
    }),
  })).filter(group => group.models.length > 0)
}
