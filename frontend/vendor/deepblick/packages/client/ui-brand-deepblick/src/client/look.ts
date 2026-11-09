/**
 * Deepblick surface language, following the product website: square surfaces
 * divided by hairlines, blue pill buttons, and the Excel selection frame (2px
 * blue with a fill handle) as the one marker for the current or chosen item.
 * Every rule is scoped to `body[data-deepblick]`, so ordinary deployments keep
 * the Harness look.
 */
import type { Context } from '@deepseek-ai/cordis'

const INK = '#16233F'
const BLUE = '#3452D6'
const BLUE_CELL = '#EAF1FF'
const LINE = '#E6E9F0'
const LINE_STRONG = '#B9C2D2'
const GREY = '#F1F2F4'

/** 2px blue frame drawn inside the box, the Excel selection. */
const SELECTION_FRAME = `inset 0 0 0 2px ${BLUE}`

/** The fill handle: a small square on the frame's bottom-right corner. */
const fillHandle = (selector: string): string => `
  ${selector} { position: relative; }
  ${selector}::after {
    content: ''; position: absolute; right: -3px; bottom: -3px; width: 6px; height: 6px;
    background: ${BLUE}; box-shadow: 0 0 0 1px #fff; pointer-events: none;
  }`

const LOOK = `
  body[data-deepblick] {
    --dsw-radius-xs: 0px; --dsw-radius-sm: 0px; --dsw-radius-md: 0px;
    --dsw-radius-lg: 0px; --dsw-radius-xl: 0px; --dsw-radius-panel: 0px;
    --dsw-focus-ring-width: 3px;
    --dsw-focus-ring-color: ${BLUE};
    caret-color: ${BLUE};
    font-variant-numeric: tabular-nums;
  }
  body[data-deepblick] ::selection { background: ${BLUE}; color: #fff; }

  /* Headings: Archivo at the website's display weight and tracking. */
  body[data-deepblick] h1, body[data-deepblick] h2, body[data-deepblick] h3,
  body[data-deepblick] h4, body[data-deepblick] [role='heading'] {
    font-weight: 800; letter-spacing: -0.03em;
  }

  /* Sidebar: tint band closed by a hairline, square rows. */
  body[data-deepblick] [class*='_sidebarCol'] { box-shadow: inset -1px 0 0 ${LINE}; }
  body[data-deepblick] [role='treeitem'],
  body[data-deepblick] [class*='_panelRow'] { border-radius: 0; }
  body[data-deepblick] [role='treeitem']:not([aria-selected='true']):hover,
  body[data-deepblick] [class*='_panelRow']:hover { background: ${GREY}; }
  body[data-deepblick] [role='treeitem'][aria-selected='true'] {
    background: ${BLUE_CELL}; box-shadow: ${SELECTION_FRAME};
  }
  ${fillHandle("body[data-deepblick] [role='treeitem'][aria-selected='true']")}

  /* Buttons: brand-blue pills, text-led. */
  body[data-deepblick] [data-sidebar-new-session] {
    --dsw-alias-button-primary-fill: var(--dsw-alias-brand-primary);
    --dsw-alias-button-primary-hover: color-mix(in srgb, var(--dsw-alias-brand-primary) 85%, var(--dsw-alias-label-primary));
    border-radius: 999px; corner-shape: round; font-weight: 700; letter-spacing: -0.005em;
    min-height: 42px;
    box-shadow: 0 4px 12px -6px color-mix(in srgb, var(--dsw-alias-brand-primary) 50%, transparent);
    transition: background-color 0.3s ease, border-color 0.3s ease, box-shadow 180ms ease;
  }
  body[data-deepblick] [data-sidebar-new-session]:hover {
    box-shadow: 0 5px 16px -6px color-mix(in srgb, var(--dsw-alias-brand-primary) 65%, transparent);
    transition-duration: 0.08s;
  }
  body[data-deepblick] [data-sidebar-automation] button {
    color: var(--dsw-alias-label-secondary);
    border-radius: 999px;
    corner-shape: round;
  }
  body[data-deepblick] [data-sidebar-automation] button[aria-current='page'] {
    color: var(--dsw-alias-link);
  }
  /* The keyboard hint would clip the centred label in a narrow task pane. */
  body[data-deepblick] [data-sidebar-new-session] [class*='_newSessionShortcut'] { display: none; }
  body[data-deepblick] [data-sidebar-new-session] [class*='_newSessionLabelMask'] { mask-image: none; }

  /* Composer: a rounded field, part of the chat family like the bubbles, on a
     hairline that turns navy on hover and blue while typing. */
  body[data-deepblick] [data-composer-card] {
    border-radius: 24px; corner-shape: round; box-shadow: inset 0 0 0 1px ${LINE_STRONG};
    transition: box-shadow 0.3s ease;
  }
  body[data-deepblick] [data-composer-card]:hover { box-shadow: inset 0 0 0 1px ${INK}; transition-duration: 0.08s; }
  body[data-deepblick] [data-composer-card]:focus-within { box-shadow: ${SELECTION_FRAME}; }

  /* The conversation column is the hero grid's size container. */
  body[data-deepblick] [class*='_scrollBody'] { container-type: inline-size; }

  /* User message: the website's chat bubble, square on the speaker's corner. */
  body[data-deepblick] [class*='_bubble'] { border-radius: 16px 16px 4px 16px; corner-shape: round; }

  /* Menus: square rows; the highlighted option is the selected cell. */
  body[data-deepblick] [class*='_surface']:has(> [role='listbox'], > [role='menu']) {
    background: #fff;
    box-shadow: 0 0 0 1px ${LINE}, 0 18px 40px -18px rgba(22, 35, 63, 0.28);
  }
  body[data-deepblick] [role='option'], body[data-deepblick] [role='menuitem'] { border-radius: 0; }
  body[data-deepblick] [role='option'][aria-selected='true'] {
    background: ${BLUE_CELL}; box-shadow: ${SELECTION_FRAME};
  }

  /* Turn navigation stays beside the reading edge, with previews opening into the transcript. */
  body[data-deepblick] [data-turn-navigator] { left: 12px; right: auto; }
  body[data-deepblick] [data-turn-mark]::before {
    left: 50%; right: auto; width: 14px; height: 2px; border-radius: 0;
    background: var(--dsw-alias-link); opacity: 0.7;
    transform: translate(-50%, -50%) scaleX(0.4); transform-origin: left center;
    transition: transform 240ms cubic-bezier(0.16, 1, 0.3, 1), opacity 180ms ease;
  }
  body[data-deepblick] [data-turn-mark]:is([aria-current='true'], [aria-describedby], :focus-visible)::before {
    background: var(--dsw-alias-link); opacity: 1;
    transform: translate(-50%, -50%) scaleX(1);
  }
  body[data-deepblick] [data-turn-mark]:focus-visible::after {
    inset: 0; width: auto; border-radius: 2px;
  }
  body[data-deepblick] [data-turn-preview] { left: calc(100% + 10px); right: auto; }

  body[data-deepblick] [data-file-attachment-card='ready'],
  body[data-deepblick] [data-file-attachment-card='sent'] { border: 0; }

  body[data-deepblick] [data-ref-chip='excel'],
  body[data-deepblick] [data-cell-citation] {
    padding: 1px 5px;
    border-radius: 4px;
    color: var(--dsw-alias-link);
    background: color-mix(in srgb, var(--dsw-alias-link) 8%, transparent);
    box-decoration-break: clone;
    -webkit-box-decoration-break: clone;
  }
  body[data-deepblick] [data-cell-citation] {
    text-decoration: underline;
    text-decoration-thickness: 1px;
    text-underline-offset: 2px;
    transition: background-color 160ms ease;
  }
  body[data-deepblick] [data-cell-citation]:is(:hover, :focus-visible) {
    background: color-mix(in srgb, var(--dsw-alias-link) 16%, transparent);
  }

  body[data-deepblick] [data-chat-return-to-bottom] {
    color: var(--dsw-alias-label-primary-foreground);
    background: var(--dsw-alias-brand-primary);
    box-shadow: 0 4px 12px -4px color-mix(in srgb, var(--dsw-alias-brand-primary) 50%, transparent);
    animation: deepblick-scroll-arrive 220ms cubic-bezier(0.16, 1, 0.3, 1);
    transition: transform 160ms ease, background-color 160ms ease;
  }
  body[data-deepblick] [data-chat-return-to-bottom]:hover {
    background: color-mix(in srgb, var(--dsw-alias-brand-primary) 85%, var(--dsw-alias-label-primary));
  }
  body[data-deepblick] [data-chat-return-to-bottom] svg {
    transition: transform 180ms cubic-bezier(0.16, 1, 0.3, 1);
  }
  body[data-deepblick] [data-chat-return-to-bottom]:is(:hover, :focus-visible) svg { transform: translateY(2px); }
  body[data-deepblick] [data-chat-return-to-bottom]:active { transform: scale(0.94); }
  @container (min-width: 900px) {
    body[data-deepblick] [data-chat-return-to-bottom-slot] {
      padding-right: max(12px, calc((100% - var(--dsh-chat-content-width)) / 2 - 48px));
    }
  }
  @keyframes deepblick-scroll-arrive {
    from { opacity: 0; transform: translateY(6px) scale(0.94); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }
  @media (prefers-reduced-motion: reduce) {
    body[data-deepblick] [data-turn-mark]::before,
    body[data-deepblick] [data-cell-citation],
    body[data-deepblick] [data-chat-return-to-bottom],
    body[data-deepblick] [data-chat-return-to-bottom] svg {
      animation: none; transition: none;
    }
    body[data-deepblick] [data-chat-return-to-bottom]:is(:hover, :focus-visible) svg { transform: none; }
  }
`

/**
 * Install the Deepblick surface rules for exactly the brand plugin lifetime.
 * @param ctx - Context owning the stylesheet.
 */
export function installDeepblickLook(ctx: Context): void {
  ctx.effect(() => {
    const style = document.createElement('style')
    style.dataset.deepblickLook = ''
    style.textContent = LOOK
    document.head.appendChild(style)
    return () => { style.remove() }
  })
}
