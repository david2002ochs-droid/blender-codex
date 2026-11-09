/** Viewport placement for the Excel effort menu; coordinates belong to its own document. */

/**
 * Prefer below the trigger, flip above when needed, and bound the scrollable card.
 * @param anchor - trigger edges in viewport coordinates.
 * @param menuHeight - measured unconstrained menu height.
 * @param viewport - the visible document viewport.
 * @returns fixed coordinates, available dimensions and the actual opening side.
 */
export function placeEffortMenu(
  anchor: Pick<DOMRect, 'left' | 'top' | 'bottom' | 'width'>,
  menuHeight: number,
  viewport: { width: number; height: number; left: number; top: number },
): { left: number; top: number; width: number; maxHeight: number; side: 'top' | 'bottom' } {
  const margin = 12
  const gap = 6
  const leftEdge = viewport.left + margin
  const topEdge = viewport.top + margin
  const rightEdge = viewport.left + viewport.width - margin
  const bottomEdge = viewport.top + viewport.height - margin
  const below = Math.max(0, bottomEdge - anchor.bottom - gap)
  const above = Math.max(0, anchor.top - gap - topEdge)
  const side = below >= menuHeight || below >= above ? 'bottom' : 'top'
  const maxHeight = side === 'bottom' ? below : above
  const height = Math.min(menuHeight, maxHeight)
  const width = Math.min(anchor.width, Math.max(0, rightEdge - leftEdge))
  return {
    left: Math.max(leftEdge, Math.min(anchor.left, rightEdge - width)),
    top: Math.max(topEdge, Math.min(side === 'bottom' ? anchor.bottom + gap : anchor.top - gap - height, bottomEdge - height)),
    width,
    maxHeight,
    side,
  }
}
