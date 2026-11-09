/** Excel-only sidebar preference; unavailable browser storage keeps the current window usable. */
import { clampWidth, SIDEBAR_MAX, SIDEBAR_MIN } from './columns.ts'

const KEY = 'dsh.excel.sidebar.width'

/**
 * Restore a bounded width without requiring browser storage access.
 * @returns The saved Excel width, or the collapsed default when storage is unavailable.
 */
export function readSidebarPreference(): number {
  try {
    const value = localStorage.getItem(KEY)
    if (value === null) return 0
    const width = Number(value)
    return Number.isFinite(width) && width > 0 ? clampWidth(width, SIDEBAR_MIN, SIDEBAR_MAX) : 0
  } catch (_storageUnavailable) {
    return 0
  }
}

/**
 * Save an explicit sidebar gesture; storage failure leaves the active window unchanged.
 * @param width - Explicit sidebar width or zero for the compact rail.
 */
export function writeSidebarPreference(width: number): void {
  try { localStorage.setItem(KEY, String(width)) }
  catch (_storageUnavailable) { /* The active window retains its layout without persistence. */ }
}
