import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-experimental-excel-range/types'
import type { ConversationNodeDefinition } from '../contract/conversation.ts'
import type { UiConversation } from '../conversation/assembly.ts'
import { excelWorkbookOf } from './excel-context.ts'

interface InputBinding {
  readonly turn: number | undefined
  readonly workbookId: string | undefined
  readonly refresh?: { readonly step: number; readonly workbookId: string } | undefined
}

interface StepBinding extends InputBinding {
  readonly turn: number
  readonly step: number
}

const inputDefinition: ConversationNodeDefinition<InputBinding> = {
  kind: 'excel-input',
  match: event => event.type === 'excel/workbook-context-refresh'
    ? { id: `refresh:${event.seq}`, role: 'start' }
    : event.type === 'user/message' && event.surfaceOp === 'append' && event.data.source.kind === 'user'
      ? { id: `user:${event.data.id}`, role: 'start' } : null,
  start: (_context, match, reader) => {
    const turn = match.location.kind === 'step' || match.location.kind === 'turn' ? match.location.turn.turn : undefined
    if (match.event.type === 'excel/workbook-context-refresh') {
      const previous = reader.previous<InputBinding>('excel-input')?.state
      const input = turn !== undefined && previous?.turn === turn ? previous : undefined
      if (input?.workbookId === undefined || match.event.data.originalWorkbookId !== input.workbookId) {
        return input ?? { turn, workbookId: undefined }
      }
      const step = match.location.kind === 'step' ? match.location.step.step : undefined
      // A request in flight keeps its binding through live-stream retirement and durable replay.
      return { turn, workbookId: match.event.data.capture.workbook.id,
        refresh: step === undefined ? undefined : input.refresh?.step === step ? input.refresh
          : { step, workbookId: input.workbookId } }
    }
    if (match.event.type !== 'user/message') throw new Error('excel-input requires human input or workbook refresh')
    const text = match.event.data.content.filter(block => block.type === 'text').map(block => block.text).join('\n')
    return { turn, workbookId: excelWorkbookOf(text) }
  },
  update: context => context.state,
}

const stepDefinition: ConversationNodeDefinition<StepBinding> = {
  kind: 'excelWorkbook',
  // The loop admits human steering before the next Step's request, so packed
  // Assistant history retains the same predecessor as the first live chunk.
  match: event => event.type === 'assistant/live-chunk' || event.type === 'assistant/attempt' || (event.type === 'assistant/message' && event.surfaceOp === 'append')
    ? { id: `${event.data.turn}:${event.data.step}`, role: 'start' } : null,
  start: (_context, match, reader) => {
    const event = match.event
    if (event.type !== 'assistant/live-chunk' && event.type !== 'assistant/attempt' && event.type !== 'assistant/message') throw new Error('excelWorkbook requires Assistant output')
    const input = reader.previous<InputBinding>('excel-input')?.state
    return { turn: event.data.turn, step: event.data.step,
      workbookId: input?.turn === event.data.turn
        ? input.refresh?.step === event.data.step ? input.refresh.workbookId : input.workbookId : undefined }
  },
  update: context => context.state,
  buildLocationData: (context, scope, previous) => {
    if (scope !== 'step' || context.state === undefined) return null
    if (previous?.key === 'excelWorkbook' && previous.value === context.state) return previous
    return { kind: 'step', turn: context.state.turn, step: context.state.step, key: 'excelWorkbook', value: context.state }
  },
}

/**
 * Register immutable input-to-step binding projections for the plugin lifetime.
 * @param ctx - owning plugin context.
 * @param conversation - target-neutral Conversation registry.
 */
export function registerExcelBindings(ctx: Context, conversation: Pick<UiConversation, 'events'>): void {
  ctx.effect(() => conversation.events.register(inputDefinition))
  ctx.effect(() => conversation.events.register(stepDefinition))
}
