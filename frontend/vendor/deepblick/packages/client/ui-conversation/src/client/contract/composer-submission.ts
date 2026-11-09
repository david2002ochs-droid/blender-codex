/** Composer submission vocabulary shared by the input and settings domains. */

import type { BusyEnterBehavior } from '../../submission-settings.ts'

export type { BusyEnterBehavior } from '../../submission-settings.ts'

/** Delivery mode requested for one ordinary composer message. */
export type InputSubmitMode = BusyEnterBehavior

/** Keyboard gesture whose delivery mode the submission policy resolves. */
export type ComposerSubmitGesture = 'enter' | 'accelerated'

/** Session facts captured when a message submission starts, before asynchronous command arbitration. */
export interface MessageSubmissionState {
  /** Materialized Session identity, including before its first message. */
  readonly sessionId?: import('@deepseek-ai/dsh-session/types').SessionId
  /** Gesture-time blank state; analytics omits the ID only when true. */
  readonly blank?: boolean
  readonly model?: { readonly provider: string; readonly name: string; readonly effort?: string }
  readonly runMode: 'default' | 'plan' | 'goal'
  readonly running: boolean
}

/** Immutable occurrence and delivery intent carried by one composer attempt. */
export interface MessageSubmission {
  /** Fresh prompt RPC identity reserved before admission and asynchronous preparation. */
  readonly requestId: import('@deepseek-ai/dsh-api-session-controller/types').SessionRequestId
  readonly timestamp: number
  readonly source?: 'click' | 'enter'
  readonly mode: InputSubmitMode
  readonly state?: MessageSubmissionState
}
