/**
 * The frame-wide `shell.overlay` host for quota notices. It holds the one live
 * notice for the whole app, so leaving the Chat panel does not drop it. A
 * `shell.quota-notice` entry may replace the generic Toast for codes it claims.
 */
import { Fragment } from 'react'
import { customerErrorText, IconWarningOutlineRegular, Toast } from '@deepseek-ai/dsh-client-ui-primitives'
import type { QuotaNoticeHostProps, QuotaNoticeOwnerProps } from '../contract/slots.ts'

/**
 * @param props - the live notice, its dismissal, the chain outlet, and the locale seat.
 * @returns the notice on display, or null while none is live.
 */
export function QuotaNoticeHost({ useNotice, dismissNotice, keepNoticeOpen, renderSlotChain, t }: QuotaNoticeHostProps) {
  const notice = useNotice(current => current)
  if (notice === null) return null
  const customer = customerErrorText(notice, t)
  const owner: QuotaNoticeOwnerProps = {
    code: notice.code, message: notice.code === 'CUSTOMER_CREDITS_EXHAUSTED' ? t('message.failure.credits') : customer ?? t('message.failure.quota'), dismiss: dismissNotice, keepOpen: keepNoticeOpen,
  }
  if (customer !== undefined && notice.code !== 'CUSTOMER_CREDITS_EXHAUSTED') {
    return <Toast key={notice.seq} text={customer} icon={<IconWarningOutlineRegular size={18} />} onDone={dismissNotice} />
  }
  return (
    <Fragment key={`quota-notice-${String(notice.seq)}`}>
      {renderSlotChain('shell.quota-notice', owner, {
        fallback: <Toast text={owner.message} icon={<IconWarningOutlineRegular size={18} />} onDone={dismissNotice} />,
      })}
    </Fragment>
  )
}
