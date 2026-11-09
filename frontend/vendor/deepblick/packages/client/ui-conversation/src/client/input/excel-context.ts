import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-store'
import { z } from 'zod'
import { randomUUID } from '@deepseek-ai/dsh-util-crypto'
import type { ExcelContextConfig } from '../../excel-config.ts'

export type { ExcelContextConfig } from '../../excel-config.ts'

const CITATION_INSTRUCTION = 'Cite Excel cells as [[cite:Sheet1!A1:B2]] (quote worksheet names with spaces).'

const text = z.string().min(1)
const hostSchema = z.strictObject({ excelApi: z.discriminatedUnion('status', [
  z.strictObject({ status: z.literal('known'), version: z.string().regex(/^1\.[1-9][0-9]?$/u) }),
  z.strictObject({ status: z.literal('unknown') }),
]), contentLanguage: text.max(2048).optional(), displayLanguage: text.max(2048).optional() })
const contextSchema = z.strictObject({
  workbook: z.strictObject({ id: text, name: text.optional(), path: text.optional(), location: z.literal('unsaved').optional() }),
  worksheet: z.strictObject({ id: text, name: text }).optional(),
  selection: z.strictObject({ workbookId: text, address: text }).optional(),
  observedAt: z.iso.datetime(),
  host: hostSchema.optional(),
}).refine(context => context.selection === undefined || context.workbook.id === context.selection.workbookId)
  .refine(context => context.workbook.location !== 'unsaved' || (context.workbook.path === undefined && context.workbook.name !== undefined))

type ExcelContext = z.infer<typeof contextSchema>

/** Validated native workbook metadata with an attached selection hint. */
export type ExcelSelection = ExcelContext & { selection: NonNullable<ExcelContext['selection']> }

function contextMarker(context: ExcelContext): string {
  return `[Excel context]\n${JSON.stringify(context)}\n${CITATION_INSTRUCTION}\n[/Excel context]`
}

/**
 * Request one bounded snapshot from the configured Excel parent. Each call
 * starts immediately and owns its listener, timeout, correlation, and abort.
 * @param config - exact trusted parent origin and capture timeout.
 * @param signal - the submitting message's lifetime.
 * @param unavailable - localized capture failure notice.
 * @param target - browser document; tests provide a structural window.
 * @returns durable user-message text, or no context for a standalone document.
 */
export function captureExcelContext(
  config: ExcelContextConfig,
  signal: AbortSignal,
  unavailable: string,
  target: Window = window,
): Promise<string> | undefined {
  if (target.parent === target) return undefined
  const requestId = randomUUID()
  return new Promise<string>((resolve, reject) => {
    const finish = (result: string | Error): void => {
      target.removeEventListener('message', receive)
      signal.removeEventListener('abort', abort)
      clearTimeout(timeout)
      if (result instanceof Error) reject(result)
      else resolve(result)
    }
    const abort = (): void => { finish(new Error(unavailable)) }
    const receive = (event: MessageEvent<unknown>): void => {
      if (event.source !== target.parent || event.origin !== config.parentOrigin) return
      const envelope = z.strictObject({
        type: z.literal('dsh/excel-context/response'), version: z.literal(1), requestId: z.literal(requestId),
        context: z.unknown().optional(),
        changes: z.unknown().optional(),
        error: z.enum(['context_unavailable', 'context_too_large']).optional(),
      }).safeParse(event.data)
      if (!envelope.success) return
      if (envelope.data.error !== undefined || envelope.data.context === undefined) {
        finish(new Error(unavailable))
        return
      }
      let raw: string | undefined
      try { raw = JSON.stringify(envelope.data.context) } catch (_error) {
        finish(new Error(unavailable))
        return
      }
      if (new TextEncoder().encode(raw).byteLength > 2048) {
        finish(new Error(unavailable))
        return
      }
      const context = contextSchema.safeParse(envelope.data.context)
      if (!context.success) {
        finish(new Error(unavailable))
        return
      }
      let changes: string | undefined
      try { changes = envelope.data.changes === undefined ? undefined : JSON.stringify(envelope.data.changes) }
      catch (_invalidOptionalEvents) { /* Invalid optional observations cannot remove a valid workbook identity. */ }
      const prefix = changes !== undefined && config.changeLimits !== undefined
        && new TextEncoder().encode(changes).byteLength <= config.changeLimits.maxBytes
        ? `[Excel changes]\n${changes}\n[/Excel changes]\n\n` : ''
      finish(prefix + contextMarker(context.data))
    }
    const timeout = setTimeout(abort, config.timeoutMs)
    target.addEventListener('message', receive)
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) { abort(); return }
    try {
      target.parent.postMessage({ type: 'dsh/excel-context/request', version: 1, requestId,
        ...(config.changeLimits === undefined ? {} : { changeLimits: config.changeLimits }) }, config.parentOrigin)
    } catch (_error) { finish(new Error(unavailable)) }
  })
}

/**
 * Decode a bounded canonical logged marker without reading workbook contents.
 * @param message - text of one durable user message.
 * @returns Workbook metadata with optional selection hints, or absence for invalid/uncaptured input.
 */
export function excelSelectionOf(message: string): ExcelContext | undefined {
  const suffix = `\n${CITATION_INSTRUCTION}\n[/Excel context]`
  if (!message.endsWith(suffix)) return undefined
  const marker = /\[Excel context\]\n([^\n]*)$/u.exec(message.slice(0, -suffix.length))
  if (marker === null || new TextEncoder().encode(marker[1]).byteLength > 2048) return undefined
  let raw: unknown
  try { raw = JSON.parse(marker[1] ?? '') } catch (_error) { return undefined /* Invalid logged marker has no navigation authority. */ }
  const context = contextSchema.safeParse(raw)
  return context.success ? context.data : undefined
}

/**
 * Navigate through the same authenticated parent with a bounded operation lifetime.
 * @param config - trusted parent origin and timeout.
 * @param workbookId - response's immutable workbook binding, including authenticated refreshes before its Step.
 * @param address - validated sheet-qualified cell reference.
 * @param signal - navigation lifetime owned by the client plugin.
 * @returns completion after a matching authenticated acknowledgement; rejects on refusal/timeout.
 */
export function navigateExcelReference(
  config: ExcelContextConfig, workbookId: string, address: string, signal: AbortSignal,
): Promise<void> {
  const requestId = randomUUID()
  return new Promise<void>((resolve, reject) => {
    const finish = (ok: boolean): void => {
      window.removeEventListener('message', receive)
      signal.removeEventListener('abort', abort)
      clearTimeout(timeout)
      if (ok) resolve()
      else reject(new Error('Excel cell reference could not be opened'))
    }
    const abort = (): void => { finish(false) }
    const receive = (event: MessageEvent<unknown>): void => {
      if (event.source !== window.parent || event.origin !== config.parentOrigin) return
      const reply = z.strictObject({ type: z.literal('dsh/excel-context/navigation'), version: z.literal(1),
        requestId: z.literal(requestId), ok: z.literal(true).optional(), error: z.literal('context_unavailable').optional() }).safeParse(event.data)
      if (reply.success) finish(reply.data.ok === true && reply.data.error === undefined)
    }
    const timeout = setTimeout(abort, config.timeoutMs)
    window.addEventListener('message', receive)
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) { abort(); return }
    try { window.parent.postMessage({ type: 'dsh/excel-context/navigate', version: 1, requestId, workbookId, address }, config.parentOrigin) }
    catch (_error) { finish(false) }
  })
}

/**
 * Read the immutable workbook binding from a durable context marker.
 * @param message - Logged user message.
 * @returns Workbook binding for authenticated citation navigation.
 */
export function excelWorkbookOf(message: string): string | undefined {
  return excelSelectionOf(message)?.workbook.id
}

/**
 * Track optional native selection hints; removing one preserves captured workbook identity.
 * @param config - Trusted parent origin.
 * @returns Observable selection, bounded update handler, and removal operations.
 */
export function createExcelSelection(config: ExcelContextConfig): SnapshotStore<ExcelSelection | undefined> & {
  accept(this: void, value: ExcelContext): void
  invalidate(this: void): void
  dismiss(this: void): void
  include(this: void, message: string): string
  receive(this: void, event: MessageEvent<unknown>): void
} {
  const store = createSnapshotStore<ExcelSelection | undefined>(undefined)
  let dismissed: string | undefined
  const key = (value: ExcelContext) => `${value.workbook.id}\n${value.selection?.address ?? ''}`
  const accept = (value: ExcelContext): void => {
    if (value.selection === undefined) { store.set(undefined); return }
    if (dismissed !== undefined && key(value) !== dismissed) dismissed = undefined
    store.set(key(value) === dismissed ? undefined : { ...value, selection: value.selection })
  }
  return {
    ...store,
    accept,
    invalidate: (): void => { store.set(undefined) },
    dismiss: (): void => {
      const value = store.getSnapshot()
      if (value !== undefined) dismissed = key(value)
      store.set(undefined)
    },
    include: (message: string): string => {
      const value = excelSelectionOf(message)
      if (value === undefined || value.selection === undefined || key(value) !== dismissed) return message
      const { worksheet: _worksheet, selection: _selection, ...workbook } = value
      return message.slice(0, message.lastIndexOf('[Excel context]\n')) + contextMarker(workbook)
    },
    receive: (event: MessageEvent<unknown>): void => {
      if (event.origin !== config.parentOrigin || event.source !== window.parent) return
      const envelope = z.strictObject({ type: z.literal('dsh/excel-context/selection'), version: z.literal(1), context: contextSchema.optional(), error: z.literal('context_unavailable').optional() }).safeParse(event.data)
      if (!envelope.success) return
      if (envelope.data.error !== undefined) { store.set(undefined); return }
      if (envelope.data.context === undefined || new TextEncoder().encode(JSON.stringify(envelope.data.context)).byteLength > 2048) return
      accept(envelope.data.context)
    },
  }
}
