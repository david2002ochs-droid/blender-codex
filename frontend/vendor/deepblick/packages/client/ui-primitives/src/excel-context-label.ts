/**
 * Display-only decoding of a bounded, logged Excel selection reference.
 * @param raw - serialized context JSON from the canonical user-message wrapper.
 * @returns The selection address or workbook label, or undefined for ordinary or invalid text.
 */
export function excelContextLabel(raw: string): string | undefined {
  if (new TextEncoder().encode(raw).byteLength > 2048) return undefined
  let value: unknown
  try { value = JSON.parse(raw) } catch (_error) { return undefined /* Ordinary user text is not a context reference. */ }
  const record = (input: unknown): input is Record<string, unknown> =>
    typeof input === 'object' && input !== null && !Array.isArray(input)
  const text = (input: unknown): input is string => typeof input === 'string' && input.length > 0
  const keys = (input: Record<string, unknown>, allowed: readonly string[]): boolean =>
    Object.keys(input).every(key => allowed.includes(key))
  if (!record(value) || !record(value.workbook)) return undefined
  if (!keys(value, ['workbook', 'worksheet', 'selection', 'observedAt', 'host'])
    || !keys(value.workbook, ['id', 'name', 'path', 'location'])
    || (value.workbook.name !== undefined && !text(value.workbook.name))
    || (value.workbook.path !== undefined && !text(value.workbook.path))
    || (value.workbook.location !== undefined && (value.workbook.location !== 'unsaved'
      || !text(value.workbook.name) || value.workbook.path !== undefined))) return undefined
  if (value.host !== undefined) {
    const host = value.host
    if (!record(host) || !keys(host, ['excelApi', 'contentLanguage', 'displayLanguage'])
      || !record(host.excelApi)) return undefined
    const api = host.excelApi
    if (api.status === 'known') {
      if (!keys(api, ['status', 'version']) || typeof api.version !== 'string'
        || !/^1\.[1-9][0-9]?$/u.test(api.version)) return undefined
    } else if (api.status !== 'unknown' || !keys(api, ['status'])) return undefined
    for (const language of [host.contentLanguage, host.displayLanguage]) {
      if (language !== undefined && (!text(language) || language.length > 2048)) return undefined
    }
  }
  if (!text(value.workbook.id) || !text(value.observedAt) || !Number.isFinite(Date.parse(value.observedAt))) return undefined
  if (value.worksheet !== undefined && (!record(value.worksheet) || !keys(value.worksheet, ['id', 'name'])
    || !text(value.worksheet.id) || !text(value.worksheet.name))) return undefined
  if (value.selection !== undefined) {
    if (!record(value.selection) || !keys(value.selection, ['workbookId', 'address'])
      || !text(value.selection.address) || value.selection.workbookId !== value.workbook.id) return undefined
    return value.selection.address
  }
  if (text(value.workbook.name)) return value.workbook.name
  if (text(value.workbook.path)) return value.workbook.path.split(/[\\/]/u).filter(Boolean).at(-1) ?? value.workbook.id
  return value.workbook.id
}
