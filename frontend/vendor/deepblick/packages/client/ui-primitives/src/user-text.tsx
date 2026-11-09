/**
 * Display projection of reference forms in sent user text (bubble and queue
 * rows). The logged model text remains the single truth; this is presentation
 * only. Inline references follow the consumer's wrapping policy and keep long
 * labels within its width. A validated canonical Excel capture suffix folds
 * to its selection label. Other decoration sources, by precedence: the wire session form
 * `@[label](dsh-session:...)` folds to its label; exact session labels
 * supplied by an adjacent recall decorate their bare `@label` mention; plain
 * `@name` word-boundary tokens decorate by shape alone; and a plain `/name`
 * token decorates only when the caller names it — a skill the host actually
 * loaded for that message (ui-chat reads the step's `skill-invocation`
 * injections) or the command a command-input bubble echoes — so `/123` or a
 * stray `/word` stays plain text. A `/name` token is whitespace-bounded like
 * the host skill gesture (`dsh-tool-skill`): it ends at whitespace or the
 * text end, so slash paths (`/nfs-hg/xxx`, `/plan.md`) and punctuation-glued
 * tokens (`/plan。`) stay plain even for a loaded name.
 */
import type { ReactNode } from 'react'
import clsx from 'clsx'
import { ReferenceIconRegular } from './ReferenceIcon.tsx'
import css from './user-text.module.css'
import markdownCss from './markdown/MarkdownText.module.css'
import { excelContextLabel } from './excel-context-label.ts'

/** The wire form a session chip serializes to; label is the display text. */
const SESSION_WIRE_RE = /@\[([^\]\n]+)\]\(dsh-session:[^)\s]+\)/gu

/** Sentence punctuation a bare `@name` token may carry without being part of the reference. */
const TRAILING_PUNCTUATION_RE = /[.,;:!?，。；：！？]+$/u

interface DecorationRange {
  readonly start: number
  readonly end: number
  /** Matched source text (hover title). */
  readonly label: string
  readonly kind: 'session' | 'excel' | 'plain'
  /** Pre-resolved display text (wire folds); derived from label when absent. */
  readonly display?: string
}

/** Only the canonical appended capture can replace text with an Excel chip. */
function excelReferenceOf(text: string): (DecorationRange & { display: string }) | undefined {
  const match = new RegExp(/(?:^|\n\n)\[Excel context\]\n([^\n]*)\n/.source
    + /Cite Excel cells as \[\[cite:Sheet1!A1:B2\]\] \(quote worksheet names with spaces\)\./.source
    + /\n\[\/Excel context\]$/.source, 'u').exec(text)
  if (match === null) return undefined
  const label = match[0].startsWith('\n\n') ? match[0].slice(2) : match[0]
  const display = excelContextLabel(match[1] ?? '')
  let start = text.length - label.length
  const changes = /(?:^|\n\n)\[Excel changes\]\n([^\n]*)\n\[\/Excel changes\]\n\n$/u.exec(text.slice(0, start))
  if (display !== undefined && changes && new TextEncoder().encode(changes[1] ?? '').length <= 8192) {
    try {
      const observation: unknown = JSON.parse(changes[1] ?? '')
      const capture: unknown = JSON.parse(match[1] ?? '')
      if (observation !== null && typeof observation === 'object' && 'workbookId' in observation
        && 'generation' in observation && typeof observation.generation === 'string'
        && 'revision' in observation && Number.isSafeInteger(observation.revision)
        && 'events' in observation && Array.isArray(observation.events) && observation.events.length <= 200
        && capture !== null && typeof capture === 'object' && 'workbook' in capture
        && capture.workbook !== null && typeof capture.workbook === 'object' && 'id' in capture.workbook
        && observation.workbookId === capture.workbook.id) {
        start = changes.index + (changes[0].startsWith('\n\n') ? 2 : 0)
      }
    } catch (_invalidEvents) { /* Malformed event wrappers remain ordinary visible text. */ }
  }
  return display === undefined ? undefined
    : { start, end: text.length, label: text.slice(start), kind: 'excel', display }
}

/**
 * Fold the appended Excel capture to its visible selection label for clipboard use.
 * @param text - Joined user-message text; other references retain their wire text.
 * @returns User text with only a validated canonical Excel suffix folded.
 */
export function userTextForCopy(text: string): string {
  const excel = excelReferenceOf(text)
  return excel === undefined ? text : text.slice(0, excel.start) + excel.display
}

/** Optional navigation supplied by consumers that can preview references. */
export interface UserTextReferences {
  /** Open a file path decoded from an `@` mention. */
  openFile: (path: string) => void
  /** Open the source of a skill loaded for this message. */
  openSkill: (name: string) => void
}

/**
 * Split one sent text into inline plain runs and reference chips.
 * @param text - the logged model text of the message or queue row.
 * @param sessionLabels - exact session mention labels associated by an adjacent recall.
 * @param slashNames - names a `/name` token may decorate as: the skills the
 * host loaded for this message, or the command a command bubble echoes
 * (unsent queue rows pass none).
 * @param slashKind - the chip kind those tokens render as.
 * @param references - optional file and skill preview actions; session and command tokens stay labels.
 * @returns inline nodes covering the whole text.
 */
export function projectUserText(
  text: string,
  sessionLabels: readonly string[],
  slashNames: readonly string[] = [],
  slashKind: 'skill' | 'command' = 'skill',
  references?: UserTextReferences,
): ReactNode {
  const ranges: DecorationRange[] = []
  const excel = excelReferenceOf(text)
  if (excel !== undefined) ranges.push(excel)
  SESSION_WIRE_RE.lastIndex = 0
  let wire: RegExpExecArray | null
  while ((wire = SESSION_WIRE_RE.exec(text)) !== null) {
    ranges.push({
      start: wire.index,
      end: wire.index + wire[0].length,
      label: wire[0],
      kind: 'session',
      display: wire[1] as string, // non-optional capture in SESSION_WIRE_RE
    })
  }
  for (const rawLabel of [...new Set(sessionLabels)].sort((a, b) => b.length - a.length)) {
    const label = `@${rawLabel}`
    let start = text.indexOf(label)
    while (start >= 0) {
      ranges.push({ start, end: start + label.length, label, kind: 'session' })
      start = text.indexOf(label, start + label.length)
    }
  }
  // A `/` token ends at whitespace or the text end like the host skill
  // gesture; only `@` tokens shed sentence punctuation below.
  const re = /(^|\s)(\/[\w-]+(?=\s|$)|@"[^"\n]+"|@[^\s]+)/gu
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const tokenStart = m.index + (m[1] as string).length // (^|\s) captures '' at line start
    const rawLabel = m[2] as string // non-optional alternation capture
    const label = rawLabel.startsWith('@"')
      ? rawLabel
      : rawLabel.replace(TRAILING_PUNCTUATION_RE, '')
    if (label.length <= 1) continue
    if (label.startsWith('/') && !slashNames.includes(label.slice(1))) continue
    ranges.push({ start: tokenStart, end: tokenStart + label.length, label, kind: 'plain' })
  }
  const rankOf = (range: DecorationRange): number => range.kind === 'plain' ? 1 : 0
  ranges.sort((a, b) => a.start - b.start || rankOf(a) - rankOf(b) || b.end - a.end)
  const parts: ReactNode[] = []
  let cursor = 0
  const pushPlain = (from: number, to: number): void => {
    parts.push(<span key={`t${from}`} className={css.plainRun}>{text.slice(from, to)}</span>)
  }
  for (const range of ranges) {
    if (range.start < cursor) continue
    const { start: tokenStart, end, label, kind } = range
    if (tokenStart > cursor) pushPlain(cursor, tokenStart)
    if (kind === 'excel') {
      parts.push(<span key={tokenStart} className={css.refChip} data-ref-chip="excel" title={range.display}>
        <ReferenceIconRegular kind="file" size={16} className={css.refIcon} />
        {range.display}
      </span>)
      cursor = end
      continue
    }
    const referenceKind = kind === 'session'
      ? 'session'
      : label.startsWith('@')
        ? label.replace(/^@"|"$/gu, '').endsWith('/') ? 'folder' : 'file'
        : undefined
    const displayLabel = range.display
      ?? (referenceKind === undefined
        ? label
        : referenceKind === 'session'
          ? label.slice(1)
          : label.slice(1).replace(/^"|"$/gu, '').split(/[\\/]/u).filter(Boolean).at(-1) ?? label.slice(1))
    const contents = <>
      {referenceKind !== undefined && (
        <ReferenceIconRegular kind={referenceKind} size={16} className={css.refIcon} />
      )}
      {displayLabel}
    </>
    const open = references === undefined ? undefined
      : referenceKind === 'file'
        ? () => { references.openFile(label.slice(1).replace(/^"|"$/gu, '')) }
        : referenceKind === undefined && slashKind === 'skill'
          ? () => { references.openSkill(label.slice(1)) }
          : undefined
    const className = clsx(css.refChip, referenceKind === undefined && css.slashChip)
    parts.push(open === undefined
      ? <span key={tokenStart} className={className} data-ref-chip={referenceKind ?? slashKind} title={label}>
        {contents}
      </span>
      : <button
        key={tokenStart}
        type="button"
        className={clsx(className, markdownCss.fileMention)}
        data-ref-chip={referenceKind ?? slashKind}
        title={label}
        onClick={(event) => {
          if (event.detail > 1 || (event.detail !== 0 && event.currentTarget.ownerDocument.getSelection()?.isCollapsed === false)) return
          open()
        }}
      >
        {contents}
      </button>)
    cursor = end
  }
  if (parts.length === 0) return <span className={css.plainRun}>{text}</span>
  if (cursor < text.length) pushPlain(cursor, text.length)
  return <>{parts}</>
}
