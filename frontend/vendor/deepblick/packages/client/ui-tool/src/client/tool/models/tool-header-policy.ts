/** Deployment-owned collapsed Tool header presentation. */
declare const __DSH_EXCEL_PRESENTATION__: boolean | undefined

/**
 * Keep the wire name alone in collapsed Excel rows, across every tool state.
 * @param toolName - Actual wire name, absent only for legacy direct row consumers.
 * @param expanded - Whether the row's details are visible.
 * @returns Whether to omit semantic titles and trailing header content.
 */
export function toolNameOnly(toolName: string | undefined, expanded: boolean): boolean {
  return typeof __DSH_EXCEL_PRESENTATION__ !== 'undefined' && __DSH_EXCEL_PRESENTATION__
    && !expanded && toolName !== undefined && toolName !== ''
}
