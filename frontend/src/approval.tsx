import React, {useState} from 'react';
import {Button, Input} from '@deepseek-ai/dsh-client-ui-primitives';
import {ApprovalPanel} from '../vendor/deepblick/packages/client/ui-approval/src/client/ApprovalPanel';
import {action, safely, showError} from './bridge';
import {t} from './project';

/** Backend-correlated flat forms/questions inside the original approval view. */
export function ApprovalSeat({approval}: {approval: any}) {
  const schema = approval.schema;
  const [values, setValues] = useState<Record<string, unknown>>(() => Object.fromEntries(Object.entries(schema?.properties || {}).filter(([, spec]: any) => spec.default !== undefined).map(([key, spec]: any) => [key, spec.default])));
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const kind = approval.kind || 'approval';
  const properties = Object.entries(schema?.properties || {}) as [string, any][];
  const supported = kind === 'approval' || kind === 'questions' && Array.isArray(approval.questions)
    || kind === 'form' && schema?.type === 'object' && properties.every(([, spec]) => ['string', 'boolean', 'integer', 'number', 'array'].includes(spec.type) && !spec.oneOf && (spec.type !== 'array' || spec.items?.type === 'string'));
  async function answer(outcome: string) {
    const approved = outcome === 'allowed-once';
    try {
      if (kind === 'approval') { await action('approve', {request_id: approval.request_id, approved}); return; }
      if (approved && !supported) throw new Error('This request format is unsupported. Decline it to let Codex continue.');
      if (approved && kind === 'form') {
        for (const required of schema.required || []) if (!(required in values)) throw new Error(`Provide ${required} before allowing this request.`);
      }
      if (approved && kind === 'questions') {
        for (const question of approval.questions) if (!answers[question.id]?.length) throw new Error('Answer every question before submitting.');
      }
      await action('respond', {request_id: approval.request_id, approved, ...(approved ? kind === 'form' ? {values} : {answers} : {})});
    } catch (error) { showError(error); throw error; }
  }
  if (!supported) return <div className="unsupported-request"><p>This request format has no supported input UI. No approval has been sent.</p><Button variant="outline" onClick={() => safely(answer('rejected'))}>Decline unsupported request</Button></div>;
  const detail = kind === 'form' ? <div className="request-fields">{properties.map(([key, spec]) => <label key={key}>{spec.title || key}{schema.required?.includes(key) ? ' *' : ''}
    {spec.description && <small>{spec.description}</small>}
    {spec.type === 'boolean' || spec.enum ? <select aria-label={spec.title || key} value={values[key] === undefined ? '' : JSON.stringify(values[key])} onChange={event => setValues({...values, [key]: event.target.value ? JSON.parse(event.target.value) : undefined})}><option value="">Choose…</option>{(spec.enum || [true, false]).map((value: unknown, index: number) => <option key={index} value={JSON.stringify(value)}>{spec.enumNames?.[index] || String(value)}</option>)}</select>
      : spec.type === 'array' ? <textarea aria-label={spec.title || key} value={Array.isArray(values[key]) ? (values[key] as string[]).join('\n') : ''} placeholder="One value per line" onChange={event => setValues({...values, [key]: event.target.value.split('\n').filter(Boolean)})}/>
        : <Input aria-label={spec.title || key} type={['integer', 'number'].includes(spec.type) ? 'number' : spec.format === 'password' ? 'password' : 'text'} min={spec.minimum} max={spec.maximum} minLength={spec.minLength} maxLength={spec.maxLength} value={values[key] === undefined ? '' : String(values[key])} onChange={event => setValues({...values, [key]: spec.type === 'string' ? event.target.value : Number(event.target.value)})}/>}
  </label>)}</div> : kind === 'questions' ? <div className="request-fields">{approval.questions.map((question: any) => <label key={question.id}>{question.header || question.question}<small>{question.question}</small>
    {question.options?.length > 0 && <select aria-label={question.header || question.id} value={answers[question.id]?.[0] || ''} onChange={event => setAnswers({...answers, [question.id]: [event.target.value]})}><option value="">Choose…</option>{question.options.map((option: any) => <option key={option.label} value={option.label}>{option.label}{option.description ? ` — ${option.description}` : ''}</option>)}</select>}
    <Input aria-label={`Answer ${question.header || question.id}`} type={question.isSecret ? 'password' : 'text'} value={answers[question.id]?.[0] || ''} onChange={event => setAnswers({...answers, [question.id]: [event.target.value]})}/>
  </label>)}</div> : null;
  return <>{!approval.tool_call_id && detail}<ApprovalPanel {...({matched: {key: JSON.stringify(approval.request_id), toolName: 'Codex', callId: approval.tool_call_id, reason: approval.text, answerable: true, answer},
    renderSlot: () => detail, resolveReason: (value: string) => value, t,
  } as React.ComponentProps<typeof ApprovalPanel>)}/></>;
}
