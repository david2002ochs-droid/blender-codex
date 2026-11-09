/** Deepblick's deployment palette and locally bundled typography. */
import type { Context } from '@deepseek-ai/cordis'
import type { ThemeTokenOverrides } from '@deepseek-ai/dsh-client-ui-theme/client'
import archivo from '../assets/archivo.woff2'
import manrope from '../assets/manrope.woff2'

const PALETTE: ThemeTokenOverrides = {
  '--dsw-font-family': { light: '"Manrope Variable", sans-serif', dark: '"Manrope Variable", sans-serif' },
  '--dsw-font-family-brand': { light: '"Archivo Variable", sans-serif', dark: '"Archivo Variable", sans-serif' },
  '--dsw-alias-bg-base': { light: '#ffffff', dark: 'hsl(223 45% 8%)' },
  '--dsw-alias-bg-layer-1': { light: '#F7F8FB', dark: 'hsl(223 40% 12%)' },
  '--dsw-alias-bg-layer-2': { light: '#F1F2F4', dark: 'hsl(223 32% 17%)' },
  '--dsw-alias-bg-layer-3': { light: '#ffffff', dark: 'hsl(223 40% 12%)' },
  '--dsw-alias-bg-overlay': { light: '#ffffff', dark: 'hsl(223 40% 12%)' },
  '--dsw-alias-label-primary': { light: '#16233F', dark: '#E6E9F0' },
  '--dsw-alias-label-secondary': { light: '#5B6675', dark: '#98A0AE' },
  '--dsw-alias-label-tertiary': { light: '#5B6675', dark: '#98A0AE' },
  '--dsw-alias-label-caption': { light: '#5B6675', dark: '#98A0AE' },
  '--dsw-alias-label-primary-dimmed': { light: '#16233F', dark: '#E6E9F0' },
  '--dsw-alias-menu-icon': { light: '#5B6675', dark: '#C3C9D6' },
  '--dsw-alias-brand-primary': { light: '#3452D6', dark: '#3452D6' },
  '--dsw-alias-brand-text': { light: '#16233F', dark: '#E6E9F0' },
  '--dsw-static-deepseek-500': { light: '#3452D6', dark: '#8FA8F0' },
  '--dsw-alias-button-primary-fill': { light: '#16233F', dark: '#16233F' },
  '--dsw-alias-button-elevated-fill': { light: '#ffffff', dark: 'hsl(223 32% 17%)' },
  '--dsw-alias-button-floating-fill': { light: '#ffffff', dark: 'hsl(223 40% 12%)' },
  '--dsw-alias-button-floating-hover': { light: '#EEF1FC', dark: 'hsl(223 38% 19%)' },
  '--dsw-alias-button-ghost-active-fill': { light: '#EEF1FC', dark: 'hsl(223 38% 19%)' },
  '--dsw-alias-button-ghost-active-hover': { light: '#D9E0F7', dark: 'hsl(223 32% 17%)' },
  '--dsw-alias-button-primary-hover': { light: '#101B33', dark: '#101B33' },
  '--dsw-alias-button-info-fill': { light: '#16233F', dark: '#16233F' },
  '--dsw-alias-button-info-hover': { light: '#101B33', dark: '#101B33' },
  '--dsw-specific-menu': { light: '#ffffff', dark: 'hsl(223 40% 12%)' },
  '--dsw-alias-label-primary-foreground': { light: '#ffffff', dark: '#ffffff' },
  '--dsw-alias-link': { light: '#3452D6', dark: '#8FA8F0' },
  '--dsw-alias-label-deep-diving': { light: '#3452D6', dark: '#8FA8F0' },
  '--dsw-alias-label-deep-diving-shimmer': { light: '#16233F', dark: '#E6E9F0' },
  '--dsw-alias-border-l1': { light: '#E6E9F0', dark: 'hsl(223 28% 21%)' },
  '--dsw-alias-border-l2': { light: '#E1E3E8', dark: 'hsl(223 28% 21%)' },
  '--dsw-alias-border-l3': { light: '#E1E3E8', dark: 'hsl(223 28% 21%)' },
  '--dsw-alias-border-l4': { light: '#C3C9D6', dark: 'hsl(223 40% 26%)' },
  '--dsw-alias-interactive-bg-active': { light: '#EEF1FC', dark: 'hsl(223 38% 19%)' },
  '--dsw-alias-interactive-bg-hover': { light: '#EEF1FC', dark: 'hsl(223 38% 19%)' },
  '--dsw-alias-interactive-bg-hover-solid': { light: '#EEF1FC', dark: 'hsl(223 38% 19%)' },
  '--dsw-specific-sidebar-fill': { light: '#F7F8FB', dark: 'hsl(223 40% 12%)' },
  '--dsw-specific-sidebar-nav-item-active': { light: '#EEF1FC', dark: 'hsl(223 38% 19%)' },
  '--dsw-specific-sidebar-nav-item-active-accent': { light: '#EEF1FC', dark: 'hsl(223 38% 19%)' },
  '--dsw-specific-sidebar-nav-item-hover': { light: '#EEF1FC', dark: 'hsl(223 38% 19%)' },
  '--dsw-specific-bubble': { light: '#EEF1FC', dark: 'hsl(223 45% 15%)' },
  '--dsw-specific-input-major': { light: '#ffffff', dark: 'hsl(223 40% 12%)' },
  '--dsw-alias-markdown-code-block': { light: '#F7F8FB', dark: 'hsl(223 32% 15%)' },
  '--dsw-alias-markdown-code-block-banner': { light: '#F1F2F4', dark: 'hsl(223 32% 17%)' },
  '--dsw-alias-markdown-inline-code': { light: '#F1F2F4', dark: 'hsl(223 32% 17%)' },
  '--dsw-alias-state-error-primary': { light: '#B0503C', dark: '#C96A55' },
  '--dsw-alias-interactive-bg-hover-danger': { light: '#FBF5F4', dark: 'hsl(10 26% 13%)' },
  '--dsw-alias-state-warn-primary': { light: '#B0503C', dark: '#C96A55' },
  '--dsw-alias-state-success-primary': { light: '#2F6F52', dark: '#8FA8F0' },
}

/**
 * Install the theme layer and font faces for exactly the brand plugin lifetime.
 * @param ctx - Context owning the deployment theme and style effects.
 */
export function installDeepblickTheme(ctx: Context): void {
  ctx.effect(() => ctx.theme.overrideTokens('@deepseek-ai/dsh-client-ui-brand-deepblick', PALETTE))
  ctx.effect(() => {
    const style = document.createElement('style')
    style.dataset.plugin = '@deepseek-ai/dsh-client-ui-brand-deepblick'
    style.textContent = `
      @font-face { font-family: 'Archivo Variable'; font-style: normal; font-weight: 100 900;
        font-display: swap; src: url("${archivo}") format('woff2'); }
      @font-face { font-family: 'Manrope Variable'; font-style: normal; font-weight: 200 800;
        font-display: swap; src: url("${manrope}") format('woff2'); }
      body[data-deepblick] h1, body[data-deepblick] h2, body[data-deepblick] h3,
      body[data-deepblick] h4, body[data-deepblick] [role='heading'] {
        font-family: var(--dsw-font-family-brand); font-weight: 700; letter-spacing: -0.02em;
      }
      body[data-deepblick] [data-sidebar-new-session] {
        background: var(--dsw-alias-button-primary-fill);
        border-color: var(--dsw-alias-button-primary-fill);
        color: var(--dsw-alias-label-primary-foreground);
        --dsw-alias-label-secondary: var(--dsw-alias-label-primary-foreground);
        --dsw-alias-label-tertiary: var(--dsw-alias-label-primary-foreground);
      }
      body[data-deepblick] [data-sidebar-new-session]:is(:hover, :focus-visible) {
        background: var(--dsw-alias-button-primary-hover);
        border-color: var(--dsw-alias-button-primary-hover);
      }
    `
    document.body.setAttribute('data-deepblick', '')
    document.head.appendChild(style)
    return () => { style.remove(); document.body.removeAttribute('data-deepblick') }
  })
}
