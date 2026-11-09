/** Shared plan link and lock for plan-limited composer controls. */
export const UPGRADE_PLAN_URL = 'https://www.deepblick.com/account/plan#upgrade'

/** @returns A decorative lock indicating a plan restriction. */
export function PlanLock() {
  return <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.25" aria-hidden="true">
    <rect x="3.5" y="7" width="9" height="6.5" rx="1.25" />
    <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2M8 9.25v2" />
  </svg>
}
