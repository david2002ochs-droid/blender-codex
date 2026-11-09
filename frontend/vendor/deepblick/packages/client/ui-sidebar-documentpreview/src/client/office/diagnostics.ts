/** Bounded, transient diagnostics for one Office preview read or shared conversion. */
import { randomUUID } from '@deepseek-ai/dsh-util-crypto'
import type { RemoteResult } from '@deepseek-ai/dsh-api-remotes/client'

const codes = [
  'gateway/ambiguous-endpoint', 'gateway/arguments-invalid', 'gateway/binding-invalid',
  'gateway/context-failed', 'gateway/context-not-found', 'gateway/context-unavailable',
  'gateway/definition-unavailable', 'gateway/input-invalid', 'gateway/invocation-unavailable',
  'gateway/lookup-failed', 'gateway/lookup-not-found', 'gateway/lookup-unavailable',
  'gateway/method-unavailable', 'gateway/protocol', 'gateway/provider-mismatch',
  'gateway/result-invalid', 'gateway/service-unavailable', 'gateway/signature-invalid',
  'gateway/uplink-overflow', 'gateway/internal', 'workspace-file/not-found',
  'workspace-file/outside-workspace', 'workspace-file/too-large', 'workspace-file/not-regular-file',
  'document-render/failed', 'UNKNOWN',
] as const
const reasons = [
  'input-too-large', 'output-too-large', 'invalid-document', 'unsupported-format',
  'invalid-output', 'timeout', 'unavailable', 'failed', 'busy', 'source-changed', 'UNKNOWN',
] as const
const phases = ['generation', 'authorization', 'metadata', 'render', 'UNKNOWN'] as const

/** Client RPC attempt that failed; UNKNOWN includes local failures between RPCs. */
export type OfficePreviewPhase = typeof phases[number]

/** Local copy format; never persisted or sent to a model or remote service. */
export interface OfficePreviewDiagnosticV1 {
  readonly schemaVersion: 1
  readonly correlationId: string
  readonly phase: OfficePreviewPhase
  readonly outcome: 'failed' | 'UNKNOWN'
  readonly code: typeof codes[number]
  readonly reason: typeof reasons[number]
}

/** One read owns this context until it adopts a failed shared conversion. */
export class OfficeDiagnostic {
  private diagnostic: OfficePreviewDiagnosticV1 | undefined

  constructor() {
    try { this.diagnostic = {
      schemaVersion: 1, correlationId: randomUUID(), phase: 'UNKNOWN', outcome: 'failed', code: 'UNKNOWN', reason: 'UNKNOWN',
    } } catch (_error) {
      // Diagnostics must remain optional when the host cannot supply randomness.
    }
  }

  /**
   * Observe an actual RPC without changing its result or rejection.
   * @param phase - attempted client RPC phase, never a native engine phase.
   * @param invoke - original RPC invocation.
   * @returns the unmodified RPC result.
   */
  async observe<T>(phase: OfficePreviewPhase, invoke: () => Promise<RemoteResult<T>>): Promise<RemoteResult<T>> {
    let result: RemoteResult<T>
    try { result = await invoke() } catch (error) {
      this.failed(phase)
      throw error
    }
    if (!result.ok) this.failed(phase, result.error.code,
      result.error.code === 'document-render/failed' ? result.error.details.reason : 'UNKNOWN')
    return result
  }

  /**
   * Record only finite scalars before customer error projection.
   * @param phase - actual failed RPC, or UNKNOWN for a local failure.
   * @param code - structured remote code; never inferred from text.
   * @param reason - structured conversion reason.
   */
  failed(phase: OfficePreviewPhase, code = 'UNKNOWN', reason = 'UNKNOWN'): void {
    try { this.diagnostic = this.project(phase, code, reason) } catch (_error) {
      // Optional diagnostics cannot mask the original preview failure.
    }
  }

  /**
   * Keep the identity of the conversion this reader actually joined.
   * @param shared - failed shared operation.
   */
  adopt(shared: OfficeDiagnostic): void {
    this.diagnostic = shared.failure()
  }

  /**
   * Read failure facts without retaining the source error.
   * @returns the current failure, or UNKNOWN for a local failure; absent if allocation failed.
   */
  failure(): OfficePreviewDiagnosticV1 | undefined {
    return this.diagnostic
  }

  private project(phase: OfficePreviewPhase, code: string, reason: string): OfficePreviewDiagnosticV1 | undefined {
    if (this.diagnostic === undefined) return undefined
    const safeCode = codes.find(value => value === code) ?? 'UNKNOWN'
    return {
      schemaVersion: 1, correlationId: this.diagnostic.correlationId, phase, outcome: 'failed', code: safeCode,
      reason: safeCode === 'document-render/failed' ? reasons.find(value => value === reason) ?? 'UNKNOWN' : 'UNKNOWN',
    }
  }
}

/**
 * Copy only the six V1 scalar fields, without serializing the source object.
 * @param diagnostic - current tab revision's failure diagnostic.
 * @returns at most 512 UTF-8 bytes, or undefined when safe copying is unavailable.
 */
export function serializeOfficeDiagnostic(diagnostic: OfficePreviewDiagnosticV1 | undefined): string | undefined {
  if (diagnostic === undefined) return undefined
  try {
    const id = diagnostic.correlationId
    if (typeof id !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)) return undefined
    const text = JSON.stringify({
      schemaVersion: 1, correlationId: id,
      phase: diagnostic.phase, outcome: diagnostic.outcome, code: diagnostic.code,
      reason: diagnostic.code === 'document-render/failed' ? diagnostic.reason : 'UNKNOWN',
    })
    return text
  } catch (_error) {
    // Copy diagnostics are best effort; never fall back to an error or document object.
    return undefined
  }
}
