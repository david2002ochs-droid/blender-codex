/** Confirmed processing preference beside Excel's effort picker. */
import { useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import { Button, MenuSurface, Switch, Tooltip, useAnchoredPosition, useDismissOnOutsidePointer } from '@deepseek-ai/dsh-client-ui-primitives'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { FastModeDirectory } from './fast-mode-directory.ts'
import css from './FastMode.module.css'
import { PlanLock, UPGRADE_PLAN_URL } from './plan-upgrade.tsx'

/**
 * Show the confirmed preference; enabling requires consent to the current quote.
 * @param props - Session-owned directory, composer lock and localized copy.
 * @returns Compact switch and its anchored confirmation.
 */
export function FastMode({ directory, locked, openPlans, t }: { directory: FastModeDirectory; locked: boolean; openPlans?: (() => boolean) | undefined } & PropsLocale<'model'>) {
  const state = useSyncExternalStore(fn => directory.store.subscribe(fn), () => directory.store.getSnapshot())
  const [open, setOpen] = useState(false)
  const [error, setError] = useState(false)
  const [target, setTarget] = useState(true)
  const root = useRef<HTMLDivElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  const id = useId()
  const ready = state.state === 'ready'
  const planLocked = ready && !state.allowed && !state.enabled
  const disabled = locked || !ready || state.pending || (!state.available || !state.allowed) && !state.enabled
  const restoreFocus = () => root.current?.querySelector('button')?.focus()
  const close = () => { setOpen(false); setError(false); restoreFocus() }
  useDismissOnOutsidePointer(root, open, setOpen, panel)
  const position = useAnchoredPosition({ open, anchorRef: root, panelRef: panel, side: 'top', align: 'end', gap: 8, margin: 12 })
  useLayoutEffect(() => { if (open) cancel.current?.focus() }, [open])
  useEffect(() => {
    if (!open) return
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close() }
    }
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('keydown', escape) }
  }, [open])
  useEffect(() => { if (locked || !ready) setOpen(false) }, [locked, ready])
  const change = async (enabled: boolean) => {
    if (!ready || disabled) return
    setError(false)
    setTarget(enabled)
    try { await directory.change(enabled, state.quoteVersion); close() }
    catch (_preferenceNotConfirmed) { setError(true); setOpen(true) }
  }
  const hint = !ready ? t('fast.unavailable') : !state.allowed ? t('fast.notIncluded') : t(state.enabled && !state.consentCurrent ? 'fast.renewHint' : state.stickyStandard ? 'fast.stickyHint' : state.enabled ? 'fast.onHint' : 'fast.offHint')
  return <div ref={root} className={css.root} data-enabled={ready && state.enabled} aria-busy={ready && state.pending}
    tabIndex={planLocked ? 0 : undefined} aria-label={planLocked ? t('fast.notIncluded') : undefined}>
    <Tooltip label={hint} disabled={planLocked} portal>
      <span className={css.label}>
        {planLocked ? <PlanLock /> : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true">
          <path d="M13.5 2 4 13h7l-1 9 10-12h-7l.5-8Z" />
        </svg>}
        {t('fast.label')}
      </span>
    </Tooltip>
    <Switch checked={ready && state.enabled} disabled={disabled} label={t('fast.label')}
      className={css.switch} title={planLocked ? undefined : hint} onChange={(enabled) => {
        if (enabled || ready && state.allowed && !state.consentCurrent) { setTarget(true); setError(false); setOpen(true) }
        else void change(false)
      }} />
    {planLocked && <div className={css.planBridge}><div className={css.planPopover}>
      <strong>{t('fast.notIncluded')}</strong>
      <p>{t('fast.upgradePlan')}</p>
      <a href={UPGRADE_PLAN_URL} target="_blank" rel="noopener noreferrer" onClick={(event) => {
        if (openPlans?.()) event.preventDefault()
      }}>{t('plan.viewPlans')} <span aria-hidden="true">→</span></a>
    </div></div>}
    {open && ready && createPortal(<MenuSurface ref={panel} role="dialog" aria-modal={false}
      aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`} className={css.confirmation}
      style={position ?? { visibility: 'hidden', left: 0, top: 0 }}>
      <h3 id={`${id}-title`}>{t(target ? 'fast.confirmTitle' : 'fast.disableTitle')}</h3>
      <p id={`${id}-description`}>{t(!target ? 'fast.disableDescription' : state.warning === 'up_to_2x' ? 'fast.confirmDescription' : state.warning === 'variable_cost' ? 'fast.variableDescription' : 'fast.noIncreaseDescription')}</p>
      {error && <p role="alert">{t('fast.error')}</p>}
      <div className={css.actions}>
        <Button ref={cancel} size="sm" disabled={state.pending} onClick={close}>{t('effort.cancel')}</Button>
        {target && state.enabled && !state.consentCurrent && <Button size="sm" disabled={state.pending} onClick={() => { void change(false) }}>{t('fast.disable')}</Button>}
        <Button size="sm" variant="primary" disabled={disabled || target && (!state.available || !state.allowed)} onClick={() => { void change(target) }}>{t(target ? 'fast.confirm' : 'fast.disable')}</Button>
      </div>
    </MenuSurface>, document.body)}
  </div>
}
