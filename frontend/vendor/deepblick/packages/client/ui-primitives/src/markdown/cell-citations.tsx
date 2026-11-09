import type { ReactNode } from 'react'
import css from './MarkdownText.module.css'

/** Owner-scoped navigation for validated sheet-qualified Excel citations. */
export interface MarkdownCellCitations {
  open(address: string): void
}

/**
 * Only bounded, ordered, in-workbook A1 addresses may become citation controls.
 * @param address - sheet-qualified address extracted from an Assistant text node.
 * @returns whether the address is a bounded single-cell or ordered rectangular A1 range.
 */
export function isCellCitation(address: string): boolean {
  if (address.length > 256 || address !== address.trim()) return false
  const match = /^(?:'((?:[^'\r\n]|'')+)'|([A-Za-z_][A-Za-z0-9_.]*))!(.+)$/u.exec(address)
  if (match === null) return false
  const sheet = match[1]?.replaceAll("''", "'") ?? match[2]
  if (sheet === undefined || sheet.length > 31 || /^[']|[']$/u.test(sheet) || /[\\/:?*\[\]\u0000-\u001f]/u.test(sheet)) return false
  const cell = (value: string | undefined): { column: number; row: number } | undefined => {
    const parts = /^\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})$/u.exec(value ?? '')
    if (parts?.[1] === undefined || parts[2] === undefined) return undefined
    const column = parts[1].toUpperCase().split('').reduce((result, letter) => result * 26 + letter.charCodeAt(0) - 64, 0)
    return { column, row: Number(parts[2]) }
  }
  const range = (match[3] ?? '').split(':')
  if (range.length > 2) return false
  const first = cell(range[0])
  const last = cell(range[1] ?? range[0])
  if (first === undefined || last === undefined) return false
  return first.column <= last.column && first.row <= last.row && last.column <= 16384 && last.row <= 1048576
}

/**
 * Text-node-only replacement; Markdown code and link nodes do not use this function.
 * @param text - settled Markdown text-node content.
 * @param owner - originating response's workbook-bound navigation owner.
 * @returns text with valid citation controls, retaining invalid tokens literally.
 */
export function renderCellCitations(text: string, owner: MarkdownCellCitations): ReactNode {
  const parts: ReactNode[] = []
  let cursor = 0
  for (const match of text.matchAll(/\[\[cite:([^\]\r\n]+)\]\]/gu)) {
    const address = match[1]
    if (address === undefined || !isCellCitation(address)) continue
    parts.push(text.slice(cursor, match.index))
    parts.push(<button key={match.index} type="button" className={css.fileMention} data-cell-citation title={address}
      onClick={() => { owner.open(address) }}>{address}</button>)
    cursor = match.index + match[0].length
  }
  if (cursor === 0) return text
  parts.push(text.slice(cursor))
  return parts
}
