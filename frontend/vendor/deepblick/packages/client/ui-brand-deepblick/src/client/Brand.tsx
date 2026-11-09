/** Deepblick artwork and developer-directed AI content reporting. */
import chatIcon from '../assets/lucide-message-square-plus.svg'
import clockIcon from '../assets/lucide-clock-3.svg'
import type { PropsLocale } from '@deepseek-ai/dsh-client-ui-slots'
import type { SidebarBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-sidebar/client'
import css from './Brand.module.css'

/** Open an editable report draft in the user's mail app without reading conversation or workbook data.
 * @param props - Deepblick-owned report copy.
 * @returns User-initiated mail link to the Deepblick reporting address.
 */
export function ReportAiContent({ t }: PropsLocale<'deepblick'>) {
  const href = 'mailto:info@deepblick.com?subject=' + encodeURIComponent(t('reportAiContentSubject'))
    + '&body=' + encodeURIComponent(t('reportAiContentBody'))
  return <a className={css.reportAiContent} href={href}>{t('reportAiContent')}</a>
}

export const EYE_PATH = 'M864 97.619C760.255 102.755 669.48 128.713 590.478 175.836 510.77 223.38 417.348 305.722 350.95 386.956 344.103 395.333 338.371 402.735 338.213 403.404 337.56 406.176 390.842 441.068 431 464.166 536.495 524.845 639.654 564.592 729 578.986 745.955 581.717 747.091 581.478 736.1 577.488 702.845 565.415 671.529 542.57 650.566 515.091L644.914 507.682 618.58 498.934C562.862 480.426 501.629 453.458 445.493 422.704 430.322 414.392 399.859 396.836 398.144 395.417 397.949 395.255 399.955 392.282 402.602 388.811 512.586 244.579 660.427 154.394 827.5 129.615 862.939 124.359 876.205 123.52 923.5 123.542 985.155 123.57 1024.515 127.713 1089.5 141.015 1177.176 158.962 1240.442 178.435 1305.75 207.577 1314.688 211.565 1322 214.667 1322 214.472 1322 213.694 1288.458 195.123 1271.5 186.512 1177.025 138.536 1069.266 108.721 957 99.497 938.571 97.982 880.39 96.808 864 97.619M860 222.492C894.576 234.418 930.737 260.606 949.5 287.308 953.252 292.647 953.935 293.129 960.5 295.06 1027.161 314.665 1107.525 350.494 1184.26 394.819 1193.477 400.144 1200.902 405.056 1200.76 405.736 1200.075 408.998 1136.693 480.985 1120.74 496.62 1011.747 603.438 872.918 665.38 718.5 676.088 697 677.579 640.333 676.702 619 674.548 501.35 662.668 396.053 636.434 301 595.32 277.843 585.304 277.953 585.347 280.5 587.242 284.865 590.488 316.552 607.656 334.5 616.498 438.926 667.943 547.13 695.226 673.5 701.975 779.962 707.661 888.725 687.216 970.831 646.084 1027.853 617.519 1103.151 562.286 1164.67 503.898 1178.556 490.72 1261.112 399.48 1261.746 396.613 1262.002 395.453 1257.604 392.419 1227.198 372.78 1143.043 318.425 1053.414 273.811 977.5 248.49 934.174 234.039 885.108 222.332 856 219.502L849.5 218.87 860 222.492'

/**
 * Render the original Deepblick eye in the host's requested geometry.
 * @param props - Requested mark size and host class.
 * @returns Decorative, theme-colored brand mark.
 */
export function DeepblickMark({ size, className }: SidebarBrandMarkOwnerProps & { className?: string | undefined }) {
  return <svg viewBox="250 75 1050 650" width={size} height={size} className={className} aria-hidden="true">
    <g>
      <path fill="currentColor" fillRule="evenodd" d={EYE_PATH} />
      <circle cx="799" cy="400" r="161.5" fill="none" stroke="currentColor" strokeWidth="61" />
      <circle cx="799" cy="400" r="61" fill="currentColor" />
    </g>
  </svg>
}

/** Render Hermes's decorative thinking eye while the Turn is running.
 * @returns Eye with a quiet gaze and blink, static under reduced motion.
 */
export function DeepblickThinkingEye() {
  return <span className={css.thinkingIcon} data-ui-running-icon="thinking" aria-hidden="true">
    <DeepblickMark size={20} className={css.thinkingEye} />
  </span>
}

/**
 * Render the independent sidebar wordmark.
 * @param props - Branding translator.
 * @returns Deepblick product name.
 */
export function DeepblickName({ t }: PropsLocale<'deepblick'>) {
  return <span className={css.name}>{t('name')}</span>
}

/** Column letters of the hero worksheet; the middle three hold the selection. */
const HERO_COLUMNS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']
const HERO_SELECTED = new Set(['E', 'F', 'G'])

/**
 * Render the Deepblick wordmark in an Excel selection over an empty worksheet,
 * with the Excel tagline below.
 * @param props - Branding translator.
 * @returns Product name and a smaller companion tagline.
 */
export function DeepblickHero({ t }: PropsLocale<'deepblick'>) {
  return <span className={css.hero}>
    <span className={css.sheet} aria-hidden="true" />
    <span className={css.columns} aria-hidden="true">
      {HERO_COLUMNS.map(column => <span key={column} className={css.column} data-selected={HERO_SELECTED.has(column) ? '' : undefined}>{column}</span>)}
    </span>
    <span className={css.selection}>
      <span className={css.wordmark}>{t('name')}</span>
    </span>
    <span className={css.tagline}>{t('tagline')}</span>
  </span>
}

/**
 * Render a decorative Lucide SVG in the surrounding ink color.
 * @param props - Bundled SVG URL and requested size.
 * @returns The SVG alpha mask colored by the surrounding text.
 */
function BrandIcon({ src, size = 16 }: { src: string; size?: number }) {
  return <span aria-hidden="true" className={css.icon} style={{ width: size, height: size, maskImage: `url("${src.replaceAll('"', '%22')}")` }} />
}

/** Deepblick's new-chat glyph. */
export function NewChatIcon({ size }: SidebarBrandMarkOwnerProps) { return <BrandIcon src={chatIcon} size={size} /> }

/** Deepblick's scheduled-tasks glyph. */
export function TasksIcon({ size }: SidebarBrandMarkOwnerProps) { return <BrandIcon src={clockIcon} size={size} /> }

/** Suppress a deployment-unneeded slot without changing ordinary deployments. */
export function HiddenControl() { return null }
