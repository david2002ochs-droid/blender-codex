/**
 * Model selection plugin, browser half — TWO entries over ONE per-session
 * directory owned by ModelDirectoryResolver (`ctx.modelDirectories`). The /model popupSelect
 * contribution and the composer's named `conversation.input.model` seat share
 * one Host-generation `session/modelCatalog` catalog, combine it with the Session's
 * durable model-selection projection, and submit through `session.selectModel`.
 * A switch made in either entry is what the other shows next. Failures
 * ride each entry's own retry surface (popup shell error/retry; seat menu
 * inline error) without forking the state. Addressed subagent sessions expose
 * neither entry because those Agent-bound RPCs would activate persisted
 * history outside the direct-parent continuation path.
 */
// Type-only: the carrier types, the forwarded Host-event face and the ctx.remote merge.
import type { ModelSelection } from '@deepseek-ai/dsh-api-session-controller/types'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type {} from '@deepseek-ai/dsh-api-session-controller/client'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { CommandUiContract, SelectOption } from '@deepseek-ai/dsh-client-ui-commands/client'
// Type-only: pulls the ui-conversation SlotMap merge (the input.model seat).
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
// Type-only: pulls the locale plugin's Context merge (ctx.locale).
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import type { TranslateNS } from '@deepseek-ai/dsh-client-ui-slots'
import { IconDataOutlineRegular } from '@deepseek-ai/dsh-client-ui-primitives'
import type { ModelDirectoryState } from './directory.ts'
import { ModelDirectoryResolver } from './service.ts'
import type { ModelSelectInjected } from './slots.ts'
import { ModelSelect } from './ModelSelect.tsx'
import { FastModeDirectory } from './fast-mode-directory.ts'
import type { ConnectionHandle } from '@deepseek-ai/dsh-client-connection/client'
import { WeakMapWithValues } from '@deepseek-ai/dsh-util-values'
import type { SessionBinding } from '@deepseek-ai/dsh-api-session-controller/client'
import { AccountModelSelect } from './AccountModelSelect.tsx'
import { en, zh, type ModelKey } from './locales.ts'
import { orderModelProviders } from './provider-order.ts'
import { EXCEL_MODELS_BOOT_KEY, resolveExcelModels, type ExcelModels } from '../excel-models.ts'
import { excelModelGroups } from './excel-groups.ts'

export { ModelDirectory } from './directory.ts'
export type { ModelDirectoryState } from './directory.ts'
export { ModelDirectoryResolver } from './service.ts'
export type { ModelSelectInjected } from './slots.ts'
export type { ModelKey } from './locales.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** The model selection surfaces' copy (/model popup + composer seat). */
    model: ModelKey
  }
}

/** One selectable row's id: an opaque row key (resolved by lookup, never parsed). */
function rowId(providerId: string, modelId: string): string {
  return `${providerId}/${modelId}`
}

/** Flatten the directory into popup rows; failure rows are listed for visibility but never selectable. */
function optionsOf(directory: ModelDirectoryState, t: TranslateNS<'model'>, excelModels?: ExcelModels): SelectOption[] {
  const rows: SelectOption[] = []
  for (const group of orderModelProviders(excelModelGroups(directory.groups, excelModels, t))) {
    const name = group.id === 'deepseek-account' ? t('provider.account') : group.name
    for (const model of group.models) {
      rows.push({
        id: rowId(group.id, model.id),
        label: model.name,
        group: { name: group.id, label: name },
        ...(directory.current !== null
          && directory.current.provider === group.id
          && directory.current.model === model.id
          ? { active: true } : {}),
      })
    }
  }
  for (const failure of directory.failures) {
    rows.push({
      id: `failure/${failure.id}`,
      label: failure.id === 'deepseek-account' ? t('provider.account') : failure.name,
      detail: t('option.loadError', { message: failure.message }),
    })
  }
  return rows
}

/**
 * Resolve a picked row back to its model selection by matching against the loaded
 * groups (the same data the rows were built from — ids stay opaque).
 * @param state - the session's directory snapshot.
 * @param id - the picked row id.
 * @returns the row's model selection, or undefined for failure rows / stale ids.
 */
function selectionOf(state: ModelDirectoryState, id: string): ModelSelection | undefined {
  for (const group of state.groups) {
    for (const model of group.models) {
      if (rowId(group.id, model.id) !== id) continue
      const sameRoute = state.current?.provider === group.id && state.current.model === model.id
      const reasoningEffort = sameRoute
        ? state.current?.reasoningEffort ?? model.reasoning?.defaultEffort
        : model.reasoning?.defaultEffort
      return {
        provider: group.id,
        model: model.id,
        ...reasoningEffort === undefined ? {} : { reasoningEffort },
      }
    }
  }
  return undefined
}

/** Dictionary namespace owned by this plugin. */
const NS = 'model'

/** Required services: the contribution registry, the seat's slot registry, locale, and the service's own faces. */
export const inject = ['commandUi', 'locale', 'sessions', 'slots', 'remote', 'remote.session']

/**
 * Client plugin body: mount ModelDirectoryResolver, register the `model` dictionaries,
 * then register the /model popup contribution and the composer model seat
 * over the service.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-model-selection: dictionaries')

  // Non-slot faces (the command description, the popup option builder) read
  // through the bound translate; the seat component reads the standard seat.
  const t = ctx.locale.bind(NS)
  const excelModels = resolveExcelModels(Reflect.get(globalThis, EXCEL_MODELS_BOOT_KEY))
  const registerCommand: unknown = Reflect.get(globalThis, '__DSH_MODEL_COMMAND__')
  if (registerCommand !== undefined && typeof registerCommand !== 'boolean') throw new Error('model registerCommand must be boolean')

  ctx.plugin(ModelDirectoryResolver)

  // Entry 1: the /model popupSelect over the shared directory.
  if (registerCommand !== false && excelModels?.effortPolicy === undefined) ctx.inject(['commandUi', 'modelDirectories'], (scope: ClientContext) => {
    const command = scope.get('commandUi') as CommandUiContract
    const models = scope.modelDirectories
    const sessions = scope.sessions
    scope.effect(() => command.register({
      name: 'model',
      label: () => t('command.label'),
      description: () => t('command.description'),
      icon: IconDataOutlineRegular,
      available: session => sessions.subagentAddress(session.sessionId) === undefined,
      ui: {
        kind: 'popupSelect',
        searchMode: 'fuzzy-label',
        searchLabels: () => ({
          placeholder: t('search.placeholder'),
          empty: t('empty.models'),
          noResults: t('search.empty'),
        }),
        options: async (session) => {
          if (sessions.subagentAddress(session.sessionId) !== undefined) {
            throw new Error('model selection is unavailable for addressed subagent sessions')
          }
          return optionsOf(await models.directoryFor(session.sessionId).load(), t, excelModels)
        },
        onSelect: async (option, session) => {
          if (sessions.subagentAddress(session.sessionId) !== undefined) {
            throw new Error('model selection is unavailable for addressed subagent sessions')
          }
          const directory = models.directoryFor(session.sessionId)
          const selection = selectionOf(directory.store.getSnapshot(), option.id)
          if (selection === undefined) {
            throw new Error('this provider\'s catalog failed to load — pick a model from a loaded group')
          }
          const result = await directory.select(selection)
          if (!result.ok) {
            if (result.error.code === 'session/writer-held') throw new Error(t('error.sessionInUse'))
            throw result.error
          }
        },
      },
    }), 'ui-model-selection: /model contribution')
  })

  // Entry 2: the composer's named model seat over the SAME directory.
  ctx.inject(['slots', 'modelDirectories'], (scope: ClientContext) => {
    const models = scope.modelDirectories
    const sessions = scope.sessions
    const fastEnabled = excelModels?.effortPolicy !== undefined && Reflect.get(globalThis, '__DSH_EXCEL_FAST__') === true
    const fastDirectories = new WeakMapWithValues<SessionBinding, FastModeDirectory>()
    scope.on('connection/reset', () => { for (const fast of fastDirectories.values) fast.resetConnected() })
    const injectSelection = (sessionId: SessionId): ModelSelectInjected => {
      const directory = models.directoryFor(sessionId)
      const available = sessions.subagentAddress(sessionId) === undefined
      const binding = sessions.binding(sessionId)
      let fastMode = binding === undefined ? undefined : fastDirectories.get(binding)
      if (fastEnabled && available && binding !== undefined && fastMode === undefined) {
        const connection = scope.get('connection') as ConnectionHandle | undefined
        if (connection === undefined) throw new Error('Excel Fast requires the Host connection')
        fastMode = new FastModeDirectory(connection.rpc, sessionId)
        fastDirectories.set(binding, fastMode)
        const owned = fastMode
        binding.ctx.effect(() => () => { owned.dispose(); fastDirectories.delete(binding) }, 'ui-model-selection: Fast preference')
        if (excelModels.effortPolicy?.kind !== 'openai') void fastMode.load()
      }
      return {
        fastMode,
        available,
        excelModels,
        isBlank: () => sessions.binding(sessionId)?.session.getSnapshot().blank === true,
        directory: directory.store,
        load: () => {
          if (available) directory.load().catch(() => { /* surfaced on the store */ })
        },
        select: (selection: ModelSelection) => available
          ? directory.select(selection)
          : Promise.resolve(undefined),
      }
    }
    if (excelModels?.effortPolicy?.kind === 'openai') {
      scope.inject(['excelEffortAccess'], account => account.slots.inject('conversation.input.model', () => account.slots.register({
        name: 'conversation.input.model', locale: NS,
        inject: sessionId => ({
          ...injectSelection(sessionId),
          openPlans: account.excelEffortAccess.openPlans,
          hooks: { effortAccess: account.excelEffortAccess },
        }),
      }, AccountModelSelect)))
    } else scope.slots.inject('conversation.input.model', () => scope.slots.register({
      name: 'conversation.input.model', locale: NS, inject: injectSelection,
    }, ModelSelect))
  })
}
