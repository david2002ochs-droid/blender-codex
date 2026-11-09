/** Opt-in Deepblick brand occupants; ordinary deployments retain their own identity. */
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@deepseek-ai/dsh-client-ui-chat/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import { DeepblickHero, DeepblickMark, DeepblickName, DeepblickThinkingEye, HiddenControl, NewChatIcon, ReportAiContent, TasksIcon } from './Brand.tsx'
import { installDeepblickTheme } from './theme.ts'
import { installDeepblickIcons } from './icons.ts'
import { installDeepblickLook } from './look.ts'
import { en, zh, type DeepblickKey } from './locales.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Deepblick name and Excel identity. */
    deepblick: DeepblickKey
  }
}

/** Services used by the brand's reversible registrations. */
export const inject = ['slots', 'locale', 'theme']

/**
 * Occupy the deployment-owned brand slots.
 * @param ctx - Browser plugin context.
 */
export function apply(ctx: Context): void {
  installDeepblickTheme(ctx)
  installDeepblickIcons(ctx)
  installDeepblickLook(ctx)
  ctx.slots.inject('conversation.chat.running.icon', () => ctx.slots.register({ name: 'conversation.chat.running.icon' }, DeepblickThinkingEye))
  ctx.slots.inject('conversation.chat.assistant-actions', () => ctx.slots.register({
    name: 'conversation.chat.assistant-actions', id: 'deepblick-report-ai-content', order: 10, locale: 'deepblick',
  }, ReportAiContent))
  const t = ctx.locale.bind('deepblick')
  for (const id of ['appearance', 'developer-tools', 'language']) {
    ctx.slots.inject('settings.general.item', () => ctx.slots.register({ name: 'settings.general.item', id, priority: -1 }, HiddenControl))
  }
  ctx.slots.inject('settings.action', () => ctx.slots.register({ name: 'settings.action', id: 'open-document', priority: -1 }, HiddenControl))
  ctx.slots.inject('conversation.session.header.corner', () => ctx.slots.register({ name: 'conversation.session.header.corner', priority: -1 }, HiddenControl))
  ctx.slots.inject('sidebar.new-session.icon', () => ctx.slots.register({ name: 'sidebar.new-session.icon' }, NewChatIcon))
  ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({ name: 'sidebar.panellist', id: 'schedules', order: 10, priority: -1, label: () => t('tasks') }, TasksIcon))
  ctx.effect(() => ctx.locale.register('deepblick', { zh, en }))
  ctx.slots.inject('sidebar.brand.mark', () => ctx.slots.register({ name: 'sidebar.brand.mark' }, DeepblickMark))
  ctx.slots.inject('sidebar.brand.name', () => ctx.slots.register({ name: 'sidebar.brand.name', locale: 'deepblick' }, DeepblickName))
  ctx.slots.inject('conversation.hero.brand.mark', () => ctx.slots.register({ name: 'conversation.hero.brand.mark' }, HiddenControl))
  ctx.slots.inject('conversation.hero.brand.name', () => ctx.slots.register({ name: 'conversation.hero.brand.name', locale: 'deepblick' }, DeepblickHero))
}
