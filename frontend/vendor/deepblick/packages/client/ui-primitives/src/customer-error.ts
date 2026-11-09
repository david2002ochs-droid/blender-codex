/** Deepblick-only projection of diagnostics to locale-owned customer feedback. */

declare const __DSH_EXCEL_PRESENTATION__: boolean | undefined

/** Customer error categories; original codes remain in the diagnostic records. */
export type CustomerErrorKey = `customerError.${'capacity' | 'auth' | 'network' | 'request' | 'requestTooLarge' | 'workbook' | 'failed' | 'outcomeUnknown' | 'changesPossible'}`

const KEYS = new Set<CustomerErrorKey>([
  'customerError.capacity', 'customerError.auth', 'customerError.network',
  'customerError.request', 'customerError.requestTooLarge', 'customerError.workbook', 'customerError.failed',
  'customerError.outcomeUnknown', 'customerError.changesPossible',
])

const CANONICAL: Readonly<Record<string, CustomerErrorKey>> = {
  AUTH: 'customerError.auth', INVALID_CREDENTIAL: 'customerError.auth', MISSING_CREDENTIAL: 'customerError.auth',
  ACCOUNT_SIGNED_OUT: 'customerError.auth', ACCOUNT_SIGN_IN_REQUIRED: 'customerError.auth',
  QUOTA: 'customerError.capacity', ACCOUNT_QUOTA: 'customerError.capacity', RATE_LIMIT: 'customerError.capacity',
  NETWORK: 'customerError.network', TRANSPORT: 'customerError.network', TIMEOUT: 'customerError.network',
  INVALID_REQUEST: 'customerError.request', INVALID_ARGS: 'customerError.request',
  CONTEXT_WINDOW_EXCEEDED: 'customerError.request', UNKNOWN_MODEL: 'customerError.request', UNSUPPORTED_CONTENT: 'customerError.request',
}

const UNAVAILABLE_RESOURCE = new RegExp(
  String.raw`\b(?:models?|providers?|upstream|service|servers?|endpoints?)\b[^\n]{0,160}`
  + String.raw`\b(?:unavailable|not (?:currently )?available|at capacity|busy|is down)\b`,
  'i',
)

/** Read only diagnostic fields, including non-enumerable Error causes, without evaluating accessors. */
function details(value: unknown): string[] {
  const pending = [value]
  const seen = new Set<object>()
  const result: string[] = []
  while (pending.length > 0) {
    const current = pending.pop()
    if (typeof current === 'string' || typeof current === 'number') { result.push(String(current)); continue }
    if (current === null || typeof current !== 'object' || seen.has(current)) continue
    seen.add(current)
    const keys = Array.isArray(current) ? Object.keys(current) : [
      'name', 'code', 'status', 'statusCode', 'message', 'type', 'cause', 'error', 'errors',
      'body', 'response', 'data', 'details', 'text', 'content', 'metadata', 'raw', 'responseBody', 'reason', 'category',
    ]
    for (const key of keys) {
      const descriptor = Object.getOwnPropertyDescriptor(current, key)
      if (descriptor !== undefined && 'value' in descriptor) pending.push(descriptor.value)
    }
  }
  return result
}

/**
 * Project a failure only when the Deepblick deployment requests customer copy.
 * Does not modify the supplied diagnostic or any Session/model data.
 * @param failure - Structured diagnostic, cause chain, or unstructured upstream response.
 * @returns A locale key carried in presentation fields, or undefined in standard Harness deployments.
 */
export function customerErrorKey(failure: unknown): CustomerErrorKey | undefined {
  if (typeof __DSH_EXCEL_PRESENTATION__ === 'undefined' || !__DSH_EXCEL_PRESENTATION__) return undefined
  const rootCode: unknown = typeof failure === 'object' && failure !== null
    ? Object.getOwnPropertyDescriptor(failure, 'code')?.value : undefined
  const canonical = typeof rootCode === 'string' && Object.hasOwn(CANONICAL, rootCode) ? CANONICAL[rootCode] : undefined
  const parts = details(failure)
  const projected = parts.find((part): part is CustomerErrorKey => KEYS.has(part as CustomerErrorKey))
  const raw = parts.join(' ')
  const text = raw.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' ')
  const codes = new Set(parts.map(part => part.trim().replace(/[_-]/g, ' ').toUpperCase()))
  const hasCode = (...values: string[]): boolean => values.some(value => codes.has(value))
  const statuses = parts.filter(part => /^\d{3}$/.test(part))
  for (const match of raw.matchAll(/(?:\bHTTP(?:\/[\d.]+)?\s+|["'](?:code|status|statusCode)["']\s*:\s*)(\d{3})\b/gi)) {
    statuses.push(match[1] as string)
  }
  for (const match of raw.matchAll(/(?:^|\n)\s*(\d{3})(?=\s|:)/g)) {
    statuses.push(match[1] as string)
  }
  const hasStatus = (...values: number[]): boolean => values.some(value => statuses.includes(String(value)))
  const requestTooLarge = hasCode('REQUEST TOO LARGE') || hasStatus(413)
  if (canonical !== undefined && (!requestTooLarge || canonical === 'customerError.auth')) return canonical
  if (projected !== undefined) return projected
  if (hasCode('TOOL OUTCOME UNKNOWN') || /\bexecution and release are unconfirmed\b/i.test(text)) return 'customerError.outcomeUnknown'
  // Specific non-capacity failures take precedence over wrapper availability wording.
  if (hasCode('AUTH', 'INVALID CREDENTIAL', 'MISSING CREDENTIAL', 'ACCOUNT SIGNED OUT', 'ACCOUNT SIGN IN REQUIRED')
    || hasStatus(401, 403)
    || /\b(?:unauthori[sz]ed|unauthenticated|not authenticated|forbidden|invalid api key|api key is invalid|authentication (?:failed|error|required|denied))\b/i.test(text)) return 'customerError.auth'
  if (requestTooLarge) return 'customerError.requestTooLarge'
  if (hasCode('CONTEXT WINDOW EXCEEDED', 'INVALID ARGS', 'INVALID REQUEST', 'UNKNOWN MODEL', 'UNSUPPORTED CONTENT')
    || /\b(?:context length exceeded|maximum context (?:length|window)|invalid (?:request|argument|args)|bad request|model not found)\b/i.test(text)) return 'customerError.request'
  if (hasCode('NETWORK', 'TRANSPORT', 'TIMEOUT')
    || /\b(?:ECONN\w*|ENOTFOUND|EAI AGAIN|ETIMEDOUT|timed out|fetch failed|socket (?:closed|hang up)|connection (?:failed|lost|reset|refused)|network (?:service )?(?:error|failure|unavailable))\b/i.test(text)) return 'customerError.network'
  if (hasCode('PROTOCOL') || /"category"\s*:\s*"protocol"/i.test(raw)) return 'customerError.failed'
  if (hasCode('QUOTA', 'ACCOUNT QUOTA', 'RATE LIMIT', 'UNAVAILABLE', 'SERVICE UNAVAILABLE', 'RESOURCE EXHAUSTED')
    || hasStatus(402, 429, 502, 503, 504, 529)
    || UNAVAILABLE_RESOURCE.test(text)
    || /\b(?:quota(?:\s+\w+){0,3}\s+(?:exceeded|exhausted|reached)|insufficient quota|exceeded (?:your )?(?:current )?quota|RATE LIMIT(?:ED)?|too many requests|overloaded|overload|out of capacity|over capacity|no capacity|insufficient (?:credits?|balance|funds)|not enough (?:credits?|balance|funds)|requires? more credits|can only afford|credit balance (?:is )?too low|(?:budget|balance|credits?)(?:\s+\w+){0,3}\s+(?:exceeded|exhausted|depleted|reached)|(?:exceeded|exhausted|depleted)(?:\s+\w+){0,3}\s+(?:budget|balance|credits?)|out of (?:credits?|budget)|payment required|billing hard limit|spending limit|spend limit|key limit exceeded|usage limit|service unavailable|resource exhausted|capacity (?:exceeded|exhausted)|temporarily unavailable|(?:upstream|provider|model|server|endpoint) (?:capacity|unavailable)|no (?:available )?(?:providers?|endpoints?))\b/i.test(text)) return 'customerError.capacity'
  if (hasStatus(400, 422)) return 'customerError.request'
  if (/\b(?:workbook|worksheet|Excel|VBA|OfficeExtension)\b/i.test(text)) return 'customerError.workbook'
  return 'customerError.failed'
}

/**
 * Localize customer feedback without returning any part of the diagnostic.
 * @param failure - Original diagnostic or the presentation fields produced from it.
 * @param t - Namespace translator with the shared customer-error vocabulary.
 * @returns Neutral localized copy, or undefined when diagnostic presentation is enabled.
 */
export function customerErrorText(failure: unknown, t: (key: CustomerErrorKey) => string): string | undefined {
  const key = customerErrorKey(failure)
  return key === undefined ? undefined : t(key)
}

/**
 * Localize failed tool output, including native execution failures carried as successful tool transport.
 * @param result - Original tool name, transport outcome and content; selected user data is not an outcome.
 * @param t - Translator with the shared customer-error vocabulary.
 * @returns Neutral failure text, or undefined for successful results and standard deployments.
 */
export function customerToolErrorText(result: {
  readonly name: string
  readonly isError: boolean
  readonly content: readonly { readonly type: string; readonly text?: string }[]
}, t: (key: CustomerErrorKey) => string): string | undefined {
  if (result.name !== 'excel_vba' && result.name !== 'execute_office_js') {
    return result.isError ? customerErrorText(result, t) : undefined
  }
  for (const block of result.content) {
    if (block.type !== 'text' || block.text === undefined) continue
    let value: unknown
    try { value = JSON.parse(block.text) }
    catch (_nonJsonOutput) { continue }
    if (value === null || typeof value !== 'object') continue
    const nativeFailure = result.name === 'excel_vba' && 'success' in value && value.success === false
    const officeFailure = result.name === 'execute_office_js' && 'kind' in value && value.kind === 'office-js'
      && 'execution' in value && ['rejected', 'failed', 'interrupted'].includes(String(value.execution))
    if (!nativeFailure && !officeFailure) continue
    if ('execution' in value && value.execution === 'unknown' || 'settlement' in value && value.settlement === 'unknown') {
      return customerErrorText({ code: 'customerError.outcomeUnknown' }, t)
    }
    if ('effects' in value && value.effects === 'possible' || 'mutation' in value && value.mutation !== 'none'
      || 'execution' in value && value.execution === 'returned') {
      return customerErrorText({ code: 'customerError.changesPossible' }, t)
    }
    return customerErrorText(value, t)
  }
  return result.isError ? customerErrorText(result, t) : undefined
}
