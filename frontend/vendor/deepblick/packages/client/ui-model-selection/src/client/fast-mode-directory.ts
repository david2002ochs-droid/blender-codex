/** Session-bound processing preference, refreshed from the Host after reconnect. */
import { createSnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { ClientConnectionRpc } from '@deepseek-ai/dsh-client-connection/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'

/** Server-confirmed state; provider tariffs and routing remain outside the Client. */
export type FastModeState = { state: 'loading' | 'unavailable' } | {
  state: 'ready'
  enabled: boolean
  pending: boolean
  warning: 'up_to_2x' | 'variable_cost' | 'no_increase'
  available: boolean
  allowed: boolean
  stickyStandard: boolean
  consentCurrent: boolean
  quoteVersion: string
}

function readState(value: unknown, sessionId: SessionId): FastModeState {
  if (typeof value !== 'object' || value === null) throw new Error('fast_response_invalid')
  const enabled: unknown = Reflect.get(value, 'fast')
  const warningObject: unknown = Reflect.get(value, 'cost_warning')
  if (typeof warningObject !== 'object' || warningObject === null) throw new Error('fast_response_invalid')
  const warning: unknown = Reflect.get(warningObject, 'kind')
  const available: unknown = Reflect.get(value, 'flex_enabled')
  const allowed: unknown = Reflect.get(value, 'fast_allowed')
  const stickyStandard: unknown = Reflect.get(value, 'sticky_standard')
  const quoteVersion: unknown = Reflect.get(value, 'consent_token')
  const consentCurrent: unknown = Reflect.get(value, 'consent_current')
  if (Reflect.get(value, 'session_id') !== sessionId || Reflect.get(value, 'contract_version') !== 1 || typeof enabled !== 'boolean'
    || (warning !== 'up_to_2x' && warning !== 'variable_cost' && warning !== 'no_increase')
    || typeof available !== 'boolean' || typeof allowed !== 'boolean' || typeof stickyStandard !== 'boolean' || typeof consentCurrent !== 'boolean'
    || typeof quoteVersion !== 'string' || !/^[a-f0-9]{64}$/.test(quoteVersion)) throw new Error('fast_response_invalid')
  return { state: 'ready', enabled, pending: false, warning, available, allowed, stickyStandard, consentCurrent, quoteVersion }
}

/** Own one Session's RPC lifetime and publish state only after a successful response. */
export class FastModeDirectory {
  /** Current confirmed preference and transport readiness for this Session. */
  readonly store = createSnapshotStore<FastModeState>({ state: 'loading' })
  private lifetime = new AbortController()
  private revision = 0

  /**
   * @param rpc - Authenticated Host transport.
   * @param sessionId - Session whose preference is being edited.
   */
  constructor(private readonly rpc: ClientConnectionRpc, private readonly sessionId: SessionId) {}

  /** Refresh the preference, rejecting stale responses from a prior connection. */
  async load(): Promise<void> {
    const revision = ++this.revision
    this.store.set({ state: 'loading' })
    try {
      const result = await this.rpc.call('/excel-fast', 'read', { sessionId: this.sessionId }, this.lifetime.signal)
      if (revision !== this.revision || this.lifetime.signal.aborted) return
      if (!result.ok) throw new Error('fast_unavailable')
      this.store.set(readState(result.value, this.sessionId))
    } catch (_preferenceUnavailable) {
      if (revision === this.revision && !this.lifetime.signal.aborted) this.store.set({ state: 'unavailable' })
    }
  }

  /**
   * Apply a confirmed user preference without changing any in-flight model request.
   * @param enabled - Whether subsequent calls should request Standard processing.
   * @param quoteVersion - Quote the user saw before confirming.
   */
  async change(enabled: boolean, quoteVersion: string): Promise<void> {
    const before = this.store.getSnapshot()
    if (before.state !== 'ready' || before.pending || before.quoteVersion !== quoteVersion || enabled && (!before.allowed || !before.available)) throw new Error('fast_quote_changed')
    const revision = ++this.revision
    this.store.set({ ...before, pending: true })
    try {
      const result = await this.rpc.call('/excel-fast', 'set', { sessionId: this.sessionId, enabled,
        ...(enabled ? { quoteVersion } : {}) }, this.lifetime.signal)
      if (revision !== this.revision || this.lifetime.signal.aborted) throw new Error('fast_connection_changed')
      if (!result.ok) throw new Error('fast_not_confirmed')
      const next = readState(result.value, this.sessionId)
      if (next.state !== 'ready' || next.enabled !== enabled) throw new Error('fast_not_confirmed')
      this.store.set(next)
    } catch (error) {
      if (revision === this.revision && !this.lifetime.signal.aborted) {
        await this.load()
        const confirmed = this.store.getSnapshot()
        if (confirmed.state === 'ready' && confirmed.enabled === enabled && (!enabled || confirmed.consentCurrent)) return
      }
      throw error
    }
  }

  /** Discard account-bound state before a sign-out or account replacement is displayed. */
  invalidate(): void {
    this.revision++
    this.lifetime.abort()
    this.store.set({ state: 'unavailable' })
  }

  /** Repull account-bound state after a connection generation changes. */
  resetConnected(): void {
    this.lifetime.abort()
    this.lifetime = new AbortController()
    void this.load()
  }

  /** Abort pending RPC and prevent late publication after the Session scope ends. */
  dispose(): void { this.revision++; this.lifetime.abort() }
}
