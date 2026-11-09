/**
 * ModelSelect's injected face. The target 'conversation.input.model' seat is
 * declared (children table) and typed by ui-conversation's composer-bar
 * entry; this package only contributes the single occupant, so no SlotMap
 * merge lives here.
 */
import type { RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import type { ModelSelection } from '@deepseek-ai/dsh-api-remotes/client'
import type { ObservableSnapshot, SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { ModelDirectoryState } from './directory.ts'
import type { ExcelModels } from '../excel-models.ts'
import type { ExcelEffortChoice } from './excel-efforts.ts'
import type { FastModeDirectory } from './fast-mode-directory.ts'

/** Account-owned product rights; the Client never maps subscription tiers or Credits to these values. */
export type ExcelEffortAccess = { state: 'loading' | 'unavailable' } | {
  state: 'ready'
  allowedEfforts: readonly ExcelEffortChoice['key'][]
}

/** Framework-bound account subscription for the product picker. */
export interface ModelSelectAccountInjected {
  hooks: { effortAccess: ObservableSnapshot<ExcelEffortAccess> }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    /** Read-only authoritative native account rights, invalidated on account or connection change. */
    excelEffortAccess: ObservableSnapshot<ExcelEffortAccess> & { openPlans?: () => boolean }
  }
}

/** Injected business face of the composer model seat. */
export interface ModelSelectInjected {
  /** Open the native plan panel when the account is available. */
  openPlans?: (() => boolean) | undefined
  /** Optional session-bound processing preference supplied by an Excel Host. */
  fastMode?: FastModeDirectory | undefined
  /** Optional deployment aliases; provider and reasoning metadata remain Host-owned. */
  excelModels?: ExcelModels | undefined
  /** Read gesture-time blank state without subscribing the render to an external callback. */
  isBlank?: () => boolean
  /** Whether this session supports Agent-bound model inspection and selection. */
  available: boolean
  /** The session's shared directory store (same instance the /model popup reads). */
  directory: SnapshotStore<ModelDirectoryState>
  /** Ensure the shared advisory catalog is loaded (errors land on the store). */
  load: () => void
  /**
   * Select a complete provider/model/reasoning selection.
   * @param selection - model selection and optional adapter-owned effort.
   * @returns the Host outcome, or undefined when this Session cannot select a model.
   */
  select: (selection: ModelSelection) => Promise<RemoteResult<void> | undefined>
}
