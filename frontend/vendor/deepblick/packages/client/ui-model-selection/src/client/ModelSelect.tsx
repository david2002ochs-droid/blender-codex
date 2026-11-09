/**
 * ModelSelect: the composer's named model seat (`conversation.input.model`).
 * Two-level selection per figma 496:26454's MenuDropdown: the root menu is
 * the Model / Effort row pair (label + current value + a right chevron),
 * each drilling into its own list — the provider-grouped model list over
 * the shared directory, and the effort levels. The trigger (313:14108's
 * ToggleButton) shows both: model name + effort in the caption tone.
 * Model catalogs above four entries show search, which retains focus while
 * ↑/↓ cycle the highlighted result; Enter and Tab accept it. Smaller model
 * catalogs, root panes, and effort panes move focus between rows. Escape and Shift+Tab leave a drilled pane first and otherwise close
 * back to the trigger. A drilled pane focuses the current effort or model
 * search field. Provider headings paint their background only while pinned
 * by scrolling. Clearing a query restores the full list and search focus.
 * Selecting restores trigger focus without a ring until the trigger loses focus
 * or the menu reopens. Model names match a case-insensitive ordered subsequence
 * within each provider group, ranked by
 * prefix, alignment score, then catalog order. Returning to the root pane
 * hands focus back to the cell that opened it. Data and submission ride the
 * same per-session ModelDirectory as the /model popup; exact-model reasoning
 * metadata and the selected effort come from the Host rather than a
 * client-owned vocabulary. A rejected selection announces through the shared
 * transient Toast anchored to the composer card; the in-menu strip with
 * Retry remains the catalog-load surface. While the directory's pending
 * selection is unsettled outside Excel, the trigger shows a spinner in place of its
 * chevron, and each row whose value that selection carries shows one in place
 * of its check mark.
 * Excel opens a viewport-bounded menu over the active route's advertised effort levels.
 */
import { customerErrorText } from '@deepseek-ai/dsh-client-ui-primitives'
import { MenuGroup, MenuSurface, observeStickyMenuGroups } from '@deepseek-ai/dsh-client-ui-primitives'
import {
  useEffect, useId, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore,
  type CSSProperties, type KeyboardEvent, type FocusEvent,
} from 'react'
import { createPortal } from 'react-dom'
import clsx from 'clsx'
import type { ModelReasoningEffort, ModelSelection } from '@deepseek-ai/dsh-api-remotes/client'
import {
  IconCheckOutlineRegular, IconChevronDownOutlineRegular, IconChevronRightOutlineRegular, IconCloseFillRegular,
  IconDataOutlineRegular, IconWarningOutlineRegular, Input, rankByName, StateDot, Toast, Modal, Button,
} from '@deepseek-ai/dsh-client-ui-primitives'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { ExcelEffortAccess, ModelSelectInjected } from './slots.ts'
import css from './ModelSelect.module.css'
import { FastMode } from './FastMode.tsx'
import { PlanLock, UPGRADE_PLAN_URL } from './plan-upgrade.tsx'
import { orderModelProviders } from './provider-order.ts'
import { excelModelGroups } from './excel-groups.ts'
import { placeEffortMenu } from './effort-placement.ts'
import { excelEfforts, needsEffortConfirmation, sameSelection } from './excel-efforts.ts'

/** Which pane the dropdown shows: the two-row root or one drilled-in list. */
type Pane = 'root' | 'model' | 'effort'

/** One dynamic effort row; undefined means preserve the provider default. */
interface EffortChoice {
  key: string
  effort: string | undefined
  label: string
  selection?: ModelSelection
  available?: boolean
  planLocked?: boolean
}

/** Unplaced portal card: hidden but laid out at a fixed origin so offsetWidth/offsetHeight are real (Menu primitive's measure pass). */
const MEASURE_STYLE: CSSProperties = { visibility: 'hidden', left: 0, top: 0 }

/**
 * Render the composer model seat.
 * @param props - owner share (locked) + injected face (shared directory
 * store/verbs) + the standard locale seat.
 * @returns the trigger and, while open, the two-level menu.
 */
export function ModelSelect(props: ModelSelectInjected & { locked: boolean; effortAccess?: ExcelEffortAccess } & PropsLocale<'model'>) {
  if (!props.available) return null
  return <div className={css.pickers}>
    {props.fastMode !== undefined && <FastMode directory={props.fastMode} locked={props.locked} openPlans={props.openPlans} t={props.t} />}
    <ModelPicker {...props} />
  </div>
}

/** Existing model/effort interaction, isolated from the sibling processing preference. */
function ModelPicker(
  { locked, available, directory, load, select, t, excelModels, isBlank, effortAccess, openPlans }:
  ModelSelectInjected & { locked: boolean; effortAccess?: ExcelEffortAccess } & PropsLocale<'model'>,
) {
  const state = useSyncExternalStore(
    fn => directory.subscribe(fn),
    () => directory.getSnapshot(),
  )
  const [open, setOpen] = useState(false)
  const [confirmation, setConfirmation] = useState<ModelSelection | null>(null)
  const [pane, setPane] = useState<Pane>('root')
  const [query, setQuery] = useState('')
  const [highlightedIndex, setHighlightedIndex] = useState<number | null>(null)
  const [selectionFocus, setSelectionFocus] = useState(false)
  // The in-menu error strip serves catalog loads (its Retry re-runs the
  // load); a rejected SELECTION announces through the transient toast
  // instead, so the strip renders only while the latest failure-capable
  // action was a load.
  const lastActionRef = useRef<'load' | 'select'>('load')
  const [toast, setToast] = useState<{ seq: number; text: string } | null>(null)
  const toastSeq = useRef(0)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const searchRef = useRef<HTMLInputElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const groupsRef = useRef<HTMLDivElement | null>(null)
  const [menuPos, setMenuPos] = useState<CSSProperties | null>(null)
  const [effortPosition, setEffortPosition] = useState<ReturnType<typeof placeEffortMenu> | null>(null)
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([])
  const id = useId()

  const groups = useMemo(() => orderModelProviders(excelModelGroups(state.groups, excelModels, t)), [state.groups, excelModels, t])
  const choices = useMemo(() => groups.flatMap(group =>
    group.models.map(model => ({
      group,
      model,
      selection: {
        provider: group.id,
        model: model.id,
        ...model.reasoning?.defaultEffort === undefined
          ? {}
          : { reasoningEffort: model.reasoning.defaultEffort },
      } satisfies ModelSelection,
    }))), [groups])
  const showSearch = choices.length > 4
  const filteredGroups = useMemo(() => groups.map(group => ({
    ...group, models: rankByName(group.models, showSearch ? query.trim() : ''),
  })).filter(group => group.models.length > 0), [groups, query, showSearch])
  const visibleModels = useMemo(() => filteredGroups.flatMap(group => group.models.map(model => ({
    provider: group.id, model: model.id,
  }))), [filteredGroups])
  const currentVisibleIndex = visibleModels.findIndex(model =>
    model.provider === state.current?.provider && model.model === state.current.model)
  const activeModelIndex = Math.min(highlightedIndex ?? Math.max(0, currentVisibleIndex), visibleModels.length - 1)
  const selectedIndex = state.current === null
    ? -1
    : choices.findIndex(c => c.selection.provider === state.current?.provider && c.selection.model === state.current.model)
  const currentChoice = choices[selectedIndex]
  const reasoning = currentChoice?.model.reasoning
  const effectiveEffort = state.current?.reasoningEffort ?? reasoning?.defaultEffort
  const productChoices = useMemo(() => excelEfforts(excelModels, state.groups), [excelModels, state.groups])
  const selectedProduct = productChoices?.find(choice => sameSelection(state.current, choice.selection))
  const excelEffortLabels = useMemo(() => excelModels === undefined ? undefined : new Map([
    ['low', t('effort.low')], ['medium', t('effort.medium')], ['high', t('effort.high')], ['max', t('effort.max')],
  ]), [excelModels, t])
  const effortLabel = productChoices !== undefined
    ? selectedProduct === undefined ? t('effort.unavailableProduct') : t(`effort.${selectedProduct.key}`)
    : reasoning === undefined
      ? excelModels === undefined ? state.retainedEffort : t('effort.unavailableProduct')
      : effectiveEffort === undefined || excelModels !== undefined && effectiveEffort === 'off'
        ? t(excelModels === undefined ? 'effort.providerDefault' : 'effort.unavailableProduct')
        : excelEffortLabels?.get(effectiveEffort) ?? reasoning.efforts.find(level => level.id === effectiveEffort)?.name ?? effectiveEffort
  const effortChoices = useMemo<readonly EffortChoice[]>(() => productChoices !== undefined
    ? productChoices.map(choice => ({ key: `product:${choice.key}`, effort: choice.selection.reasoningEffort,
      label: t(`effort.${choice.key}`), selection: choice.selection, available: choice.available,
      planLocked: excelModels?.effortPolicy?.kind === 'openai' && effortAccess?.state === 'ready'
        && !effortAccess.allowedEfforts.includes(choice.key) }))
    : reasoning === undefined
      ? []
      : [
        ...excelModels === undefined && reasoning.defaultEffort === undefined
          ? [{ key: 'provider-default', effort: undefined, label: t('effort.providerDefault') }]
          : [],
        ...reasoning.efforts.filter(effort => excelModels === undefined || effort.id !== 'off').map((effort: ModelReasoningEffort) => ({
          key: `effort:${effort.id}`,
          effort: effort.id,
          label: excelEffortLabels?.get(effort.id) ?? effort.name,
        })),
      ], [reasoning, t, excelModels, excelEffortLabels, productChoices, effortAccess])
  const isSelected = (level: EffortChoice): boolean => level.selection === undefined
    ? effectiveEffort === level.effort : sameSelection(state.current, level.selection)
  const accountRequired = excelModels?.effortPolicy?.kind === 'openai'
  const canSelectProduct = (selection: ModelSelection): boolean => productChoices?.some(choice => choice.available
    && sameSelection(selection, choice.selection) && (excelModels?.effortPolicy?.kind === 'openai-direct-developer'
      || accountRequired && effortAccess?.state === 'ready' && effortAccess.allowedEfforts.includes(choice.key))) === true
  const { pending } = state
  const busy = pending !== null

  const reload = (): void => {
    lastActionRef.current = 'load'
    load()
  }

  useEffect(() => {
    if (!open) return
    const closeOutside = (event: MouseEvent): void => {
      // The portaled card is outside the trigger subtree; check both.
      if (rootRef.current?.contains(event.target as Node) === true) return
      if (menuRef.current?.contains(event.target as Node) === true) return
      setOpen(false)
    }
    document.addEventListener('mousedown', closeOutside)
    return () => { document.removeEventListener('mousedown', closeOutside) }
  }, [open])

  useLayoutEffect(() => {
    if (!showSearch) {
      setQuery('')
      setHighlightedIndex(null)
    }
  }, [showSearch])

  // Pane or account-right changes can unmount the focused row; restore focus inside the menu so
  // keyboard navigation remains available.
  const paneFocus = useRef<'drill' | 'model' | 'effort' | null>(null)
  const previousShowSearch = useRef(showSearch)
  useEffect(() => {
    const changedSearchMode = previousShowSearch.current !== showSearch
    previousShowSearch.current = showSearch
    const active = document.activeElement
    const disabledOptionFocused = active instanceof HTMLButtonElement && active.disabled && menuRef.current?.contains(active)
    const intent = paneFocus.current ?? (changedSearchMode && pane === 'model'
      || excelModels !== undefined && effortPosition !== null && (active === document.body || disabledOptionFocused) ? 'drill' : null)
    paneFocus.current = null
    if (!open || intent === null) return
    // A browser cannot focus an option in the hidden measurement portal.
    if (excelModels !== undefined && effortPosition === null) {
      paneFocus.current = intent
      return
    }
    if (intent === 'drill') {
      if (excelModels !== undefined && effortChoices.length === 0) {
        paneFocus.current = 'drill'
        triggerRef.current?.focus()
        return
      }
      if (pane === 'model' && showSearch) {
        searchRef.current?.focus()
        return
      }
      // The checked row is the value in use; a pane without one opens on its
      // first row.
      const checked = menuRef.current?.querySelector<HTMLElement>('[role="menuitemradio"][aria-checked="true"]:not([disabled])')
      const target = checked ?? itemRefs.current.find(item => item !== null && !item.disabled)
      // Rows a selection in flight disabled cannot take the keyboard; the
      // trigger does, so the card's keys still reach the menu.
      ;(target ?? triggerRef.current)?.focus()
      return
    }
    const cell = itemRefs.current[intent === 'effort' && excelModels === undefined ? 1 : 0]
    ;(cell !== null && cell !== undefined && !cell.disabled ? cell : triggerRef.current)?.focus()
  }, [open, pane, showSearch, excelModels, effortChoices, effortPosition])

  useEffect(() => {
    const viewport = groupsRef.current
    if (viewport === null) return
    return observeStickyMenuGroups(viewport)
  }, [available, open, pane, filteredGroups])

  useLayoutEffect(() => {
    if (open && pane === 'model' && activeModelIndex >= 0) {
      itemRefs.current[activeModelIndex]?.scrollIntoView({ block: 'nearest' })
    }
  }, [open, pane, activeModelIndex, visibleModels])

  // Portaled placement (the Menu primitive's portal rules: fixed from the
  // anchor rect, measured before paint, clamped inside the viewport): above
  // the trigger, right edges aligned. Depends on pane and directory state
  // because pane switches and async catalog loads resize the card.
  /* jscpd:ignore-start -- deliberate mirror of ui-primitives useAnchoredPosition:
     that hook only places from the anchor's LEFT edge, while this card aligns
     right edges (x = rect.right - width), so the measure-and-clamp plumbing repeats. */
  useLayoutEffect(() => {
    if (!open || excelModels !== undefined) { setMenuPos(null); return }
    const place = (): void => {
      /* v8 ignore next 2 -- the trigger ref is attached whenever the menu is open. */
      const rect = triggerRef.current?.getBoundingClientRect()
      if (rect === undefined) return
      const MARGIN = 12
      const lw = menuRef.current?.offsetWidth ?? 0
      const lh = menuRef.current?.offsetHeight ?? 0
      let x = rect.right - lw
      let y = rect.top - 8 - lh
      if (lw > 0) x = Math.min(Math.max(x, MARGIN), window.innerWidth - lw - MARGIN)
      if (lh > 0) y = Math.min(Math.max(y, MARGIN), window.innerHeight - lh - MARGIN)
      setMenuPos({ left: x, top: y })
    }
    // First run measures the hidden pre-render (same commit as `open`), so
    // the card lands placed before anything paints.
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, pane, state, query, excelModels])
  /* jscpd:ignore-end */

  useLayoutEffect(() => {
    if (!open || excelModels === undefined) { setEffortPosition(null); return }
    let previous: ReturnType<typeof placeEffortMenu> | null = null
    let naturalWidth = 0
    const place = (): void => {
      const anchor = triggerRef.current
      const panel = menuRef.current
      if (anchor === null || panel === null) return
      const viewport = window.visualViewport
      const rect = anchor.getBoundingClientRect()
      if (naturalWidth === 0) naturalWidth = Math.max(rect.width, panel.offsetWidth)
      const next = placeEffortMenu({ left: rect.left, top: rect.top, bottom: rect.bottom, width: naturalWidth },
        panel.scrollHeight + panel.offsetHeight - panel.clientHeight,
        { width: viewport?.width ?? window.innerWidth, height: viewport?.height ?? window.innerHeight,
          left: viewport?.offsetLeft ?? 0, top: viewport?.offsetTop ?? 0 })
      const last = previous
      if (last !== null && Object.keys(next).every(key => Reflect.get(last, key) === Reflect.get(next, key))) return
      previous = next
      setEffortPosition(next)
    }
    place()
    // Composer movement need not dispatch a viewport resize or scroll.
    let frame: number
    const track = (): void => { place(); frame = requestAnimationFrame(track) }
    frame = requestAnimationFrame(track)
    return () => { cancelAnimationFrame(frame) }
  }, [open, excelModels, effortChoices.length])

  useEffect(() => { if (locked || !available) { setOpen(false); setConfirmation(null) } }, [locked, available])

  if (!available) return null

  const show = (focus = true): void => {
    setSelectionFocus(false)
    if (focus) triggerRef.current?.focus()
    setQuery('')
    setHighlightedIndex(null)
    if (focus && (excelModels !== undefined || state.current === null)) paneFocus.current = 'drill'
    setPane(excelModels !== undefined ? 'effort' : state.current === null ? 'model' : 'root')
    setOpen(true)
    if (focus && open && excelModels !== undefined) {
      const checked = menuRef.current?.querySelector<HTMLElement>('[aria-checked="true"]:not([disabled])')
      ;(checked ?? itemRefs.current.find(item => item !== null && !item.disabled))?.focus()
    }
    reload()
  }

  const changeQuery = (next: string): void => {
    setQuery(next)
    setHighlightedIndex(0)
  }

  const close = (restoreFocus = false): void => {
    setOpen(false)
    setPane('root')
    if (restoreFocus) queueMicrotask(() => { triggerRef.current?.focus() })
  }

  const closeAfterSelection = (): void => {
    setSelectionFocus(true)
    close(true)
  }

  const drill = (next: Pane): void => {
    setQuery('')
    setHighlightedIndex(null)
    paneFocus.current = 'drill'
    setPane(next)
  }

  /** Leave a drilled pane for the root one, handing the keyboard back to its cell. */
  const back = (from: Exclude<Pane, 'root'>): void => {
    paneFocus.current = from
    setPane('root')
  }

  const moveFocus = (offset: number): void => {
    const items = excelModels === undefined ? itemRefs.current.filter(item => item !== null && !item.disabled)
      : Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('button[role="menuitemradio"]:not(:disabled)') ?? [])
    if (items.length === 0) return
    const active = items.findIndex(item => item === document.activeElement)
    // Focus outside the rows (the trigger, which keeps it while the menu
    // opens) enters at the end the step comes from: the first row forward,
    // the last row backward.
    const next = active === -1
      ? (offset > 0 ? 0 : items.length - 1)
      : (active + offset + items.length) % items.length
    items[next]?.focus()
  }

  const onRootKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    if (event.nativeEvent.isComposing) return
    if (event.key === 'Escape' && open) {
      event.preventDefault()
      // Excel closes its direct list; ordinary menus leave the drilled pane first.
      if (excelModels === undefined && pane !== 'root' && state.current !== null) back(pane)
      else close(true)
      return
    }
    if (!open && excelModels !== undefined && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
      event.preventDefault()
      show()
      return
    }
    if (!open) return
    if (excelModels !== undefined) {
      if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
        event.preventDefault()
        moveFocus(event.key === 'ArrowDown' ? 1 : -1)
      } else if (event.key === 'Home' || event.key === 'End') {
        event.preventDefault()
        const rows = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('button[role="menuitemradio"]:not(:disabled)') ?? [])
        ;(event.key === 'Home' ? rows[0] : rows.at(-1))?.focus()
      } else if (event.key === 'Tab') {
        if (event.target === triggerRef.current && !event.shiftKey && effortChoices.length > 0 && !busy) {
          event.preventDefault()
          const selected = menuRef.current?.querySelector<HTMLElement>('[aria-checked="true"]:not([disabled])')
          ;(selected ?? itemRefs.current.find(item => item !== null && !item.disabled))?.focus()
        } else close()
      }
      return
    }
    if (pane === 'model' && showSearch && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
      event.preventDefault()
      if (!busy && visibleModels.length > 0) {
        const direction = event.key === 'ArrowDown' ? 1 : -1
        setHighlightedIndex((activeModelIndex + direction + visibleModels.length) % visibleModels.length)
        searchRef.current?.focus()
      }
      return
    }
    if (pane === 'model' && showSearch && event.target instanceof HTMLInputElement
      && (event.key === 'Enter' || (event.key === 'Tab' && !event.shiftKey))) {
      if (event.key === 'Tab' && visibleModels.length === 0) return
      event.preventDefault()
      const highlighted = visibleModels[activeModelIndex]
      if (!busy && highlighted !== undefined) choose(highlighted)
      return
    }
    // Tab settles like Enter and Shift+Tab leaves like Escape, so the menu's
    // keys mean what they mean in the composer. Both are consumed: the card
    // keeps the browser's focus traversal out while it is open.
    if (event.key === 'Tab') {
      if (event.shiftKey) {
        event.preventDefault()
        if (pane !== 'root' && state.current !== null) back(pane)
        else close(true)
        return
      }
      // Settling activates the row the keyboard is on; with focus still on the
      // trigger, Tab enters the menu at the value in use instead. Any other
      // control inside the card (a retry button) keeps the browser's traversal,
      // so the keystroke stays unconsumed there.
      const focused = document.activeElement
      const rows = itemRefs.current.filter((item): item is HTMLButtonElement => item !== null)
      if (focused instanceof HTMLButtonElement && rows.includes(focused)) {
        event.preventDefault()
        focused.click()
        return
      }
      if (focused !== triggerRef.current) return
      event.preventDefault()
      if (pane === 'model' && showSearch) {
        setHighlightedIndex(null)
        searchRef.current?.focus()
        return
      }
      const checked = menuRef.current?.querySelector<HTMLElement>('[role="menuitemradio"][aria-checked="true"]:not([disabled])')
      ;(checked ?? rows.find(item => !item.disabled))?.focus()
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      moveFocus(event.key === 'ArrowDown' ? 1 : -1)
    }
  }

  const onBlur = (event: FocusEvent<HTMLDivElement>): void => {
    if (event.relatedTarget instanceof Node && (
      rootRef.current?.contains(event.relatedTarget) === true
      || menuRef.current?.contains(event.relatedTarget) === true
    )) return
    close()
  }

  const settleSelection = (result: Awaited<ReturnType<ModelSelectInjected['select']>>): void => {
    if (result === undefined) return
    if (result.ok) {
      if (rootRef.current !== null) closeAfterSelection()
      return
    }
    const { error } = result
    toastSeq.current += 1
    setToast({
      seq: toastSeq.current,
      text: error.code === 'session/writer-held'
        ? t('error.sessionInUse')
        : customerErrorText(error, t) ?? t('error.action', { message: `${error.code}: ${error.message}` }),
    })
  }

  const submit = (selection: ModelSelection): void => {
    lastActionRef.current = 'select'
    // Disabled option rows cannot retain focus while a selection is pending.
    setSelectionFocus(true)
    triggerRef.current?.focus()
    void select(selection).then(settleSelection)
  }

  const choose = (selection: ModelSelection): void => {
    if (state.current?.provider === selection.provider && state.current.model === selection.model) {
      closeAfterSelection()
      return
    }
    submit(selection)
  }

  const chooseEffort = (effort: string | undefined): void => {
    if (state.current === null) return
    if (effectiveEffort === effort) {
      closeAfterSelection()
      return
    }
    const selection: ModelSelection = {
      provider: state.current.provider,
      model: state.current.model,
      ...effort === undefined ? {} : { reasoningEffort: effort },
    }
    submit(selection)
  }

  const chooseProduct = (selection: ModelSelection): void => {
    if (!canSelectProduct(selection)) return
    if (sameSelection(state.current, selection)) { closeAfterSelection(); return }
    if (isBlank?.() !== true && needsEffortConfirmation(state.current, selection,
      excelModels?.effortPolicy?.cacheFriendlyChanges === true)) {
      close()
      setConfirmation(selection)
      return
    }
    submit(selection)
  }

  const waiting = state.current === null && state.status === 'loading'
  const modelLabel = excelModels !== undefined
    ? t('menu.effort')
    : waiting
      ? t('trigger.loading')
      : currentChoice?.model.name
        ?? (state.current === null ? t('trigger.fallback') : `${state.current.provider}/${state.current.model}`)
  const triggerLabel = effortLabel === undefined ? modelLabel : `${modelLabel} · ${effortLabel}`
  const triggerAria = excelModels !== undefined
    ? t('trigger.effortAria', { effort: effortLabel ?? t('effort.providerDefault') })
    : waiting
      ? t('trigger.loading')
      : state.current === null
        ? t('trigger.selectAria')
        : effortLabel === undefined
          ? t('trigger.aria', { model: modelLabel })
          : t('trigger.ariaEffort', { model: modelLabel, effort: effortLabel })
  itemRefs.current = []
  let itemIndex = 0
  let modelIndex = 0
  const itemRef = () => {
    const at = itemIndex++
    return (node: HTMLButtonElement | null) => { itemRefs.current[at] = node }
  }

  return (<>
    <div
      ref={rootRef}
      className={css.root}
      onKeyDown={onRootKeyDown}
      onBlur={onBlur}
      onMouseDown={(event) => {
        // WebKit blurs a focused row before click unless the button's mousedown keeps focus.
        if (event.target instanceof Element && event.target.closest('button') !== null) event.preventDefault()
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        className={clsx(css.trigger, excelModels !== undefined && css.effortTrigger)}
        aria-label={triggerAria}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? `${id}-menu` : undefined}
        title={triggerLabel}
        aria-busy={busy}
        data-selection-focus={selectionFocus ? '' : undefined}
        onBlur={() => { setSelectionFocus(false) }}
        disabled={locked}
        onClick={() => {
          if (open) {
            close(true)
          } else {
            show()
          }
        }}
      >
        {excelModels === undefined && <IconDataOutlineRegular className={css.triggerIcon} size={16} />}
        <span className={css.triggerLabel}>{modelLabel}</span>
        {excelModels !== undefined && <span className={css.effortValue}>{effortLabel ?? t('effort.unavailableProduct')}</span>}
        {excelModels === undefined && effortLabel !== undefined && <span className={css.triggerEffort}>{effortLabel}</span>}
        {busy && excelModels === undefined
          ? <StateDot state="ongoing" />
          : <IconChevronDownOutlineRegular className={clsx(css.chevron, open && css.chevronOpen)} />}
      </button>

      {open && excelModels !== undefined && createPortal(
        <MenuSurface ref={menuRef} id={`${id}-menu`} role="menu" aria-label={t('menu.effort')}
          aria-busy={state.status === 'loading' || busy} className={clsx(css.effortMenu, productChoices !== undefined && css.productEffortMenu)}
          data-side={effortPosition?.side} style={effortPosition === null ? MEASURE_STYLE : {
            left: effortPosition.left, top: effortPosition.top, width: effortPosition.width, maxHeight: effortPosition.maxHeight,
          }}>
          {effortChoices.map(level => <button key={level.key} ref={itemRef()} type="button" role="menuitemradio"
            aria-checked={isSelected(level)} aria-label={level.planLocked ? t('effort.planLocked', { effort: level.label }) : undefined}
            disabled={busy || locked || level.planLocked || level.available === false
              || level.selection !== undefined && !canSelectProduct(level.selection)}
            className={clsx(css.effortOption, isSelected(level) && !level.planLocked && css.effortSelected)}
            onClick={() => {
              if (level.selection === undefined) chooseEffort(level.effort)
              else chooseProduct(level.selection)
            }}><span>{level.label}</span>{level.planLocked ? <PlanLock /> : isSelected(level) && <IconCheckOutlineRegular aria-hidden="true" size={16} />}</button>)}
          {effortChoices.some(level => level.planLocked) && <div className={css.planFooter}>
            <div>{t('effort.unlockLevels')}</div>
            <button ref={itemRef()} type="button" role="menuitem" className={css.viewPlans}
              onClick={() => { close(); if (!openPlans?.()) window.open(UPGRADE_PLAN_URL, '_blank', 'noopener,noreferrer') }}>
              {t('plan.viewPlans')} <span aria-hidden="true">→</span>
            </button>
          </div>}
          {effortChoices.length === 0 && <span className={css.status} role="status">
            {state.status === 'loading' ? t('status.effortLoading') : t('empty.excelEfforts')}
          </span>}
          {effortChoices.length > 0 && !effortChoices.some(level => !level.planLocked && isSelected(level))
            && <span className={css.status} role="status">{productChoices === undefined
              ? t('effort.unavailable', { effort: effortLabel ?? t('effort.providerDefault') }) : t('effort.chooseAllowed')}</span>}
          {accountRequired && <>
            {effortAccess?.state !== 'ready' && <span className={css.status} role="status">{t('effort.accessUnavailable')}</span>}
          </>}
        </MenuSurface>, document.body,
      )}
      {/* Portaled to body (Menu primitive's portal mode) so the sidebar and
          column overflow clips cannot crop the card; synthetic events still
          bubble through this React subtree, keeping onKeyDown/onBlur live. */}
      {open && excelModels === undefined && createPortal(
        <MenuSurface
          ref={menuRef}
          id={`${id}-menu`}
          className={css.menu}
          style={menuPos ?? MEASURE_STYLE}
          role={pane === 'model' ? 'group' : 'menu'}
          aria-label={t('menu.aria')}
          aria-busy={state.status === 'loading' || busy}
        >
          {pane === 'root' && (
            <>
              <button ref={itemRef()} type="button" role="menuitem" className={css.cell} onClick={() => { drill('model') }}>
                <span className={css.cellLabel}>{t('menu.model')}</span>
                <span className={css.cellValue}>{modelLabel}</span>
                <IconChevronRightOutlineRegular className={css.cellChevron} />
              </button>
              {reasoning !== undefined && (
                <button ref={itemRef()} type="button" role="menuitem" className={css.cell} onClick={() => { drill('effort') }}>
                  <span className={css.cellLabel}>{t('menu.effort')}</span>
                  <span className={css.cellValue}>{effortLabel}</span>
                  <IconChevronRightOutlineRegular className={css.cellChevron} />
                </button>
              )}
            </>
          )}

          {pane === 'model' && (
            <>
              {showSearch && <div className={css.searchRow}>
                <Input
                  ref={searchRef}
                  className={clsx(css.search, query !== '' && css.searchWithQuery)}
                  type="text"
                  role="searchbox"
                  aria-label={t('search.placeholder')}
                  aria-controls={`${id}-models`}
                  aria-activedescendant={activeModelIndex < 0 ? undefined : `${id}-model-${activeModelIndex}`}
                  placeholder={t('search.placeholder')}
                  value={query}
                  readOnly={busy}
                  onChange={(event) => { changeQuery(event.target.value) }}
                />
                {query !== '' && (
                  <button
                    type="button"
                    className={css.searchClear}
                    aria-label={t('search.clear')}
                    disabled={busy}
                    onClick={() => {
                      changeQuery('')
                      searchRef.current?.focus()
                    }}
                  >
                    <IconCloseFillRegular />
                  </button>
                )}
              </div>}
              {state.status === 'loading' && (
                <div className={css.status}>{t('status.loading')}</div>
              )}
              {state.error !== null && lastActionRef.current === 'load' && (
                <div className={css.error}>
                  <span>{customerErrorText(state.error, t) ?? t('error.action', { message: state.error })}</span>
                  <button type="button" className={css.retry} onClick={reload}>{t('retry')}</button>
                </div>
              )}
              {state.failures.map(failure => (
                <div className={css.warning} key={failure.id}>
                  <span>{customerErrorText(failure.message, t) ?? t('warning.groupLoad', { name: failure.id === 'deepseek-account' ? t('provider.account') : failure.name, message: failure.message })}</span>
                  <button type="button" className={css.retry} onClick={reload}>{t('retry')}</button>
                </div>
              ))}
              <div
                ref={groupsRef}
                id={`${id}-models`}
                className={clsx(css.groups, 'scrollable')}
                role="menu"
                aria-label={t('menu.model')}
                hidden={filteredGroups.length === 0}
              >
                {filteredGroups.map((group) => {
                  return (
                    <MenuGroup key={group.id} label={group.id === 'deepseek-account' ? t('provider.account') : group.name}>
                      {group.models.map((model) => {
                        const index = modelIndex++
                        const selected = state.current?.provider === group.id && state.current.model === model.id
                        return (
                          <button
                            ref={itemRef()}
                            type="button"
                            role="menuitemradio"
                            aria-checked={selected}
                            id={`${id}-model-${index}`}
                            tabIndex={showSearch ? -1 : 0}
                            onFocus={() => { setHighlightedIndex(index) }}
                            data-highlighted={index === activeModelIndex ? '' : undefined}
                            className={clsx(
                              css.option, css.modelOption, selected && css.selected, index === activeModelIndex && css.optionActive,
                            )}
                            onMouseMove={busy || index === activeModelIndex ? undefined : () => {
                              if (showSearch) setHighlightedIndex(index)
                              else itemRefs.current[index]?.focus()
                            }}
                            key={model.id}
                            title={model.name}
                            disabled={busy}
                            onClick={() => { choose({ provider: group.id, model: model.id }) }}
                          >
                            <span className={css.optionCopy}>
                              <span className={css.modelName}>{model.name}</span>
                            </span>
                            <span className={css.check}>
                              {pending?.provider === group.id && pending.model === model.id
                                ? <StateDot state="ongoing" />
                                : selected ? <IconCheckOutlineRegular /> : null}
                            </span>
                          </button>
                        )
                      })}
                    </MenuGroup>
                  )
                })}
              </div>
              {state.status === 'ready' && filteredGroups.length === 0 && (
                <div className={css.empty} role="status">{t(choices.length === 0 ? 'empty.models' : 'search.empty')}</div>
              )}
            </>
          )}

          {pane === 'effort' && (
            <>
              {state.error !== null && lastActionRef.current === 'load' && (
                <div className={css.error}>
                  <span>{customerErrorText(state.error, t) ?? t('error.action', { message: state.error })}</span>
                  <button type="button" className={css.retry} onClick={reload}>{t('action.reload')}</button>
                </div>
              )}
              {effortChoices.length === 0
                ? <div className={css.empty}>{t('empty.efforts')}</div>
                : effortChoices.map(level => (
                  <button
                    ref={itemRef()}
                    type="button"
                    role="menuitemradio"
                    aria-checked={effectiveEffort === level.effort}
                    className={clsx(css.option, effectiveEffort === level.effort && css.selected)}
                    key={level.key}
                    disabled={busy}
                    onClick={() => { chooseEffort(level.effort) }}
                  >
                    <span className={css.optionCopy}>
                      <span className={css.modelName}>{level.label}</span>
                    </span>
                    <span className={css.check}>
                      {pending !== null && pending.provider === state.current?.provider
                        && pending.model === state.current.model && pending.reasoningEffort === level.effort
                        ? <StateDot state="ongoing" />
                        : effectiveEffort === level.effort ? <IconCheckOutlineRegular /> : null}
                    </span>
                  </button>
                ))}
            </>
          )}
        </MenuSurface>,
        document.body,
      )}
      {toast !== null && (
        <Toast
          key={toast.seq}
          text={toast.text}
          icon={<IconWarningOutlineRegular />}
          anchor={rootRef.current?.closest<HTMLElement>('[data-composer-card]') ?? null}
          onDone={() => { setToast(null) }}
        />
      )}
    </div>
    <Modal open={confirmation !== null} title={t('effort.confirmTitle')} description={t('effort.confirmDescription')}
      className={clsx(css.confirmation, 'scrollable')}
      closeLabel={t('effort.close')} onClose={() => { setConfirmation(null); triggerRef.current?.focus() }}
      footer={<><Button variant="outline" onClick={() => { setConfirmation(null); triggerRef.current?.focus() }}>{t('effort.cancel')}</Button>
        <Button variant="primary" disabled={busy || locked || confirmation !== null && !canSelectProduct(confirmation)} onClick={() => {
          const next = confirmation
          setConfirmation(null)
          if (next !== null && canSelectProduct(next)) submit(next)
        }}>{t('effort.confirm')}</Button></>} />
  </>
  )
}
