import React, {useEffect, useState} from 'react';
import {createSnapshotStore} from '@deepseek-ai/dsh-client-store';
import {InputBar} from '../vendor/deepblick/packages/client/ui-conversation/src/client/skeleton/InputBar';
import {DraftEditorRuntime} from '../vendor/deepblick/packages/client/ui-conversation/src/client/input/editor/runtime';
import {ComposerAttachments} from '../vendor/deepblick/packages/client/ui-attachment/src/client/ComposerAttachments';
import {ModelSelect} from '../vendor/deepblick/packages/client/ui-model-selection/src/client/ModelSelect';
import {PermissionSelect} from '../vendor/deepblick/packages/client/ui-permission-presets/src/client/PermissionSelect';
import {Button, Modal, IconPaperclipOutlineRegular, IconEditOutlineRegular, IconDataOutlineRegular, PermissionIconFullAccessRegular, IconGoalOutlineRegular, IconPlanOutlineRegular, IconCompactOutlineRegular, IconDownloadOutlineRegular, rankByName} from '@deepseek-ai/dsh-client-ui-primitives';
import {InputTriggerController} from '../vendor/deepblick/packages/client/ui-input-trigger/src/client/controller';
import {MenuView} from '../vendor/deepblick/packages/client/ui-input-trigger/src/client/MenuView';
import {en as triggerLocale} from '../vendor/deepblick/packages/client/ui-input-trigger/src/client/locales';
import {en as commandLocale} from '../vendor/deepblick/packages/client/ui-commands/src/client/locales';
import {sectionRows} from '../vendor/deepblick/packages/client/ui-commands/src/client/presentation';
import {PopupSelectController} from '../vendor/deepblick/packages/client/ui-commands/src/client/popup';
import {PopupSelectView} from '../vendor/deepblick/packages/client/ui-commands/src/client/PopupSelectView';
import {wire, useSource, action, safely, upload, showError, loadImage, download, type Resource} from './bridge';
import {useSession, useProjection, t, modelT, permissionT, permissionViewId, permissionWireId, translate} from './project';

const input = createSnapshotStore<any>({draft: '', attachmentIds: [], draftRev: 0, phase: 'plain', occurrences: [], queue: []});
export const useComposerInput = (select: any) => useSource(input, select);
let draftWriter: ((draft: string) => void) | undefined;
export const persistComposerDraft = () => draftWriter?.(input.getSnapshot().draft);
export function bindDraftPersistence(writer: (draft: string) => void) { draftWriter = writer; const off = input.subscribe(persistComposerDraft); return () => { off(); if (draftWriter === writer) draftWriter = undefined; }; }
const uploads = createSnapshotStore<any>({});
const notices = createSnapshotStore<any>(undefined);
const attachments = new Map<string, any>();
const admitted = new Map<string, Resource>();
const seenServerAttachments = new Set<string>();
let uploadQueue = Promise.resolve();
const emptyLexicon = new Map();
let picker: {open(): void; available(): boolean} | undefined;
let includeView = false;
const attachmentFlag = createSnapshotStore(false);
const commandT = translate(commandLocale), triggerT = translate(triggerLocale);
const goalOpen = createSnapshotStore(false);
let triggers: InputTriggerController | undefined;
export const runtime = new DraftEditorRuntime({
  onUpdate() {
    runtime.refreshProjection();
    const value = runtime.projection;
    const previous = input.getSnapshot();
    input.set({...previous, draft: value.clipboardText, draftRev: previous.draftRev + (value.clipboardText !== previous.draft ? 1 : 0)});
    triggers?.track(value.detectText, value.caret ?? value.detectText.length, {tier: 'plain'}, input.getSnapshot().draftRev);
  },
  openReference: () => false, activeClaimToken: () => null, lexicon: () => emptyLexicon, resolveLexicon: () => undefined,
});
const disposeEditor = runtime.register();
window.addEventListener('pagehide', disposeEditor);
async function submit() {
  const state = wire.getSnapshot(); const draft = input.getSnapshot();
  if (!state.ready || state.busy || state.pending.includes('send') || draft.phase !== 'plain') return;
  if (!draft.draft.trim() && !draft.attachmentIds.length) return;
  const pending = draft.attachmentIds.some((id: string) => !admitted.has(id));
  if (pending) { showError(new Error('Wait for the selected files to finish uploading.')); return; }
  input.set({...draft, phase: 'submitting'});
  try {
    await action('send', {text: draft.draft, include_view: includeView, attachment_ids: draft.attachmentIds.map((id: string) => admitted.get(id)!.id)});
    // Accepted messages are rendered only from authoritative backend snapshots.
    // No synthetic user/item ID or fabricated pending transcript is created.
    if (input.getSnapshot().draft === draft.draft) runtime.setDraft('');
    for (const id of draft.attachmentIds) removeAttachment(id);
  } catch (_) { /* Bridge error and original draft stay visible. */ }
  finally { input.set({...input.getSnapshot(), phase: 'plain'}); }
}
const keyboard = {
  editor: runtime.editor, submit: () => safely(submit()), steerQueue: () => {},
  caretSpan: () => runtime.caretSpan(), arbitrate: (key: any, composing: boolean) => triggers?.arbitrate(key, composing) || 'pass', space: () => false, dismissPopup: () => { triggers?.dismiss(); popup.dismiss(); },
  paste: (text: string) => runtime.paste(text),
  bindFilePicker(value: typeof picker) { picker = value; return () => { if (picker === value) picker = undefined; }; },
};
function removeAttachment(id: string) {
  const value = attachments.get(id);
  if (value?.previewUrl && value.file instanceof File) URL.revokeObjectURL(value.previewUrl);
  attachments.delete(id); admitted.delete(id);
  input.set({...input.getSnapshot(), attachmentIds: input.getSnapshot().attachmentIds.filter((item: string) => item !== id)});
}
async function uploadOne(id: string, file: File) {
  uploads.set({...uploads.getSnapshot(), [id]: {status: 'uploading', loaded: 0, total: file.size}});
  try {
    const resource = await upload(file);
    seenServerAttachments.add(resource.id);
    if (!attachments.has(id)) return;
    admitted.set(id, resource);
    uploads.set({...uploads.getSnapshot(), [id]: {status: 'ready', receiptId: resource.id, file: resource}});
  } catch (error) {
    uploads.set({...uploads.getSnapshot(), [id]: {status: 'error', message: error instanceof Error ? error.message : 'Upload failed.'}});
  }
}
function addFiles(files: readonly File[]) {
  if (!wire.getSnapshot().capabilities?.can_upload_attachments) return 'File uploads are not available.';
  for (const file of files) {
    // These are browser-owned draft IDs, never claimed as Codex item IDs.
    const id = crypto.randomUUID();
    const image = file.type.startsWith('image/') && file.type !== 'image/svg+xml';
    attachments.set(id, {id, kind: image ? 'image' : 'file', file, ...(image ? {previewUrl: URL.createObjectURL(file)} : {})});
    input.set({...input.getSnapshot(), attachmentIds: [...input.getSnapshot().attachmentIds, id]});
    uploads.set({...uploads.getSnapshot(), [id]: {status: 'uploading', loaded: 0, total: file.size}});
    uploadQueue = uploadQueue.then(() => uploadOne(id, file));
    safely(uploadQueue);
  }
  return null;
}
function consume(span: any) {
  if (span.draftRev !== input.getSnapshot().draftRev) return false;
  return span.start === span.end || runtime.replaceText(span, '');
}
const popup = new PopupSelectController({consume: (segment: any) => segment.via === 'menu' && consume(segment.span), focusComposer: () => runtime.editor.focus()});
function commandSource() {
  return {trigger: '/', name: 'command', showGroupTitle: false,
    async candidates(_session: any, request: any) {
      const state = wire.getSnapshot(); const rows: any[] = [];
      if (state.capabilities?.can_upload_attachments) rows.push({name: 'file', label: t('input.file'), icon: IconPaperclipOutlineRegular});
      if (state.capabilities?.can_goal) rows.push({name: 'goal', label: commandT('label.goal'), description: commandT('description.goal'), icon: IconGoalOutlineRegular});
      if (state.capabilities?.can_plan) rows.push({name: 'plan', label: commandT('label.plan'), description: commandT('description.plan'), icon: IconPlanOutlineRegular});
      if (state.capabilities?.can_compact) rows.push({name: 'compact', label: commandT('label.compact'), description: commandT('description.compact'), icon: IconCompactOutlineRegular});
      if (state.capabilities?.can_set_permission_mode && state.permission_modes?.length) rows.push({name: 'permission', label: commandT('label.permission'), description: commandT('description.permission'), icon: PermissionIconFullAccessRegular});
      if (state.capabilities?.can_select_model && state.models?.length) rows.push({name: 'model', label: modelT('command.label'), description: modelT('command.description'), icon: IconDataOutlineRegular});
      if (state.capabilities?.can_export) rows.push({name: 'export', label: commandT('label.export'), description: 'Download the observed chat snapshot', icon: IconDownloadOutlineRegular});
      if (state.capabilities?.can_draw) rows.push({name: 'draw', label: state.markup_active ? 'Zeichnen beenden' : 'Zeichnen', description: 'Blender-Ansicht markieren · Esc beendet und löscht Markierungen', icon: IconEditOutlineRegular});
      if (state.capabilities?.can_attach_view) rows.push({name: 'view', label: includeView ? 'Ansicht entfernen' : 'Ansicht anhängen', description: 'Aktuelle Ansicht beim ausdrücklichen Senden anhängen', icon: IconPaperclipOutlineRegular});
      return request.query === '' ? sectionRows(rows, commandT as any) : rankByName(rows, request.query);
    },
    onPick(pick: any) {
      const state = wire.getSnapshot(); const name = pick.candidate.name;
      if (name === 'file') { if (consume(pick.span)) picker?.open(); return 'handled'; }
      if (name === 'draw') { if (consume(pick.span)) { if (!state.markup_active) { includeView = true; attachmentFlag.set(true); } safely(action(state.markup_active ? 'markup_cancel' : 'draw')); } return 'handled'; }
      if (name === 'view') { if (consume(pick.span)) { includeView = !includeView; attachmentFlag.set(includeView); } return 'handled'; }
      if (name === 'goal') { if (consume(pick.span)) { goalOpen.set(true); safely(action('goal/get')); } return 'handled'; }
      if (name === 'compact') { if (consume(pick.span)) safely(action('compact')); return 'handled'; }
      if (name === 'plan') popup.open(name, {kind: 'popupSelect', options: async () => (state.collaboration_modes || []).map(mode => ({id: mode.mode || mode.name, label: mode.name || mode.mode, active: (mode.mode || mode.name) === state.collaboration_mode})), onSelect: option => action('set_mode', {mode: option.id})}, {sessionId: state.thread_id}, {via: 'menu', span: pick.span});
      if (name === 'export') popup.open(name, {kind: 'popupSelect', options: async () => [{id: 'markdown', label: 'Markdown'}, {id: 'json', label: 'JSON'}], onSelect: async option => { const reply = await action('export_chat', {format: option.id}); const resource = reply.resource || reply.attachment; if (!resource?.resource_url) throw new Error('No downloadable export was returned.'); await download(resource); }}, {sessionId: state.thread_id}, {via: 'menu', span: pick.span});
      if (name === 'model') popup.open(name, {kind: 'popupSelect', searchMode: 'fuzzy-label', options: async () => state.models.map(model => ({id: model.id, label: model.displayName || model.name || model.id, active: model.id === state.selected_model})), onSelect: option => action('select_model', {model_id: option.id})}, {sessionId: state.thread_id}, {via: 'menu', span: pick.span});
      if (name === 'permission') popup.open(name, {kind: 'popupSelect', options: async () => (state.permission_modes || []).map(option => ({id: option.id, label: option.label, detail: option.description, active: option.id === state.permission_mode,
        ...(permissionViewId(option.id) === 'full-access' ? {confirmation: {title: permissionT('confirm.title'), description: permissionT('confirm.description'), acknowledgeLabel: permissionT('confirm.acknowledge'), cancelLabel: permissionT('confirm.cancel'), confirmLabel: permissionT('confirm.enable')}} : {}),
      })), onSelect: option => action('set_permission_mode', {permission_mode: option.id})}, {sessionId: state.thread_id}, {via: 'menu', span: pick.span});
      return 'handled';
    },
  };
}
function bindTriggers(sessionId: string) {
  triggers?.dispose(); popup.dismiss();
  goalOpen.set(false);
  const source = commandSource();
  // This local source invokes only existing bridge capabilities. It does not
  // register a Harness runtime or manufacture a remote command catalog.
  triggers = new InputTriggerController({actx: {bail: () => false} as any, sessionId: sessionId as any, roster: {sources: trigger => trigger === '/' ? [source as any] : [], all: () => [source as any]}});
}
bindTriggers(wire.getSnapshot().thread_id || 'unconnected');
let draftThread = wire.getSnapshot().thread_id;
const threadDrafts = new Map<string, string>();
function GoalDialog() {
  const state = useSource(wire), open = useSource(goalOpen);
  const [objective, setObjective] = useState(''), [budget, setBudget] = useState(''), [dirty, setDirty] = useState(false);
  useEffect(() => { if (open && !dirty) { setObjective(state.goal?.objective || ''); setBudget(String(state.goal?.tokenBudget ?? state.goal?.token_budget ?? '')); } }, [open, state.goal, dirty]);
  useEffect(() => { if (!open) setDirty(false); }, [open]);
  if (!open) return null;
  const pending = state.pending.some(name => name.startsWith('goal/')) || state.busy;
  const setStatus = (status: string) => safely(action('goal/set', {status}).then(() => goalOpen.set(false)));
  return <Modal open onClose={() => goalOpen.set(false)} title="Goal" closeLabel="Close goal" footer={<><Button variant="outline" disabled={pending || !state.goal} onClick={() => safely(action('goal/clear').then(() => goalOpen.set(false)))}>Clear</Button><Button variant="outline" disabled={pending || !state.goal} onClick={() => setStatus(state.goal?.status === 'paused' ? 'active' : 'paused')}>{state.goal?.status === 'paused' ? 'Resume' : 'Pause'}</Button><Button variant="primary" disabled={pending || !objective.trim() || (budget !== '' && (!Number.isInteger(Number(budget)) || Number(budget) <= 0))} onClick={() => safely(action('goal/set', {objective: objective.trim(), ...(budget ? {token_budget: Number(budget)} : {})}).then(() => goalOpen.set(false)))}>Save goal</Button></>}>
    <div className="request-fields"><label>Objective<textarea aria-label="Goal objective" value={objective} onChange={event => { setDirty(true); setObjective(event.target.value); }}/></label><label>Token budget (optional)<input aria-label="Goal token budget" type="number" min="1" value={budget} onChange={event => { setDirty(true); setBudget(event.target.value); }}/></label></div>
    {state.goal?.status && <p role="status">Status: {state.goal.status}</p>}{state.ui_error && <p role="alert" className="bridge-error">{state.ui_error}</p>}
  </Modal>;
}
const permissionCatalog = createSnapshotStore<any>({value: null});
const modelDirectory = createSnapshotStore<any>({current: null, routable: null, groups: [], failures: [], status: 'idle', pending: null, error: null});
wire.subscribe(() => {
  const state = wire.getSnapshot();
  if (state.thread_id !== draftThread) {
    if (draftThread) threadDrafts.set(draftThread, input.getSnapshot().draft);
    for (const id of [...attachments.keys()]) removeAttachment(id);
    draftThread = state.thread_id;
    seenServerAttachments.clear();
    includeView = false; attachmentFlag.set(false);
    bindTriggers(state.thread_id || 'unconnected');
    runtime.setDraft(state.thread_id ? threadDrafts.get(state.thread_id) || '' : '');
  }
  const used = new Set(state.messages.flatMap(message => (message.attachments || []).map(item => typeof item === 'string' ? item : item.id)));
  for (const resource of state.attachments) {
    if (seenServerAttachments.has(resource.id) || used.has(resource.id) || [...admitted.values()].some(value => value.id === resource.id)) continue;
    // Original generated images and explicit annotation commits arrive from the
    // separate editor host. Their true server handles enter this local draft.
    seenServerAttachments.add(resource.id);
    const id = resource.id;
    const value = {id, kind: 'file', file: {name: resource.name, size: resource.size || 0, type: resource.mime_type}};
    attachments.set(id, value); admitted.set(id, resource);
    uploads.set({...uploads.getSnapshot(), [id]: {status: 'ready', receiptId: resource.id, file: resource}});
    input.set({...input.getSnapshot(), attachmentIds: [...input.getSnapshot().attachmentIds, id]});
    if (resource.mime_type.startsWith('image/')) safely(loadImage(resource).then(url => {
      if (attachments.get(id) !== value) return;
      attachments.set(id, {...value, kind: 'image', previewUrl: url}); input.set({...input.getSnapshot()});
    }));
  }
  const groups = state.models?.length ? [{id: 'codex', name: 'Codex', models: state.models.map((model: any) => ({
    id: model.id, name: model.displayName || model.name || model.id,
    ...(model.supportedReasoningEfforts?.length ? {reasoning: {efforts: model.supportedReasoningEfforts.map((effort: any) => ({id: effort.reasoningEffort, name: effort.reasoningEffort, description: effort.description})), defaultEffort: model.defaultReasoningEffort}} : {}),
  }))}] : [];
  const next = {current: state.selected_model ? {provider: 'codex', model: state.selected_model, reasoningEffort: state.reasoning_effort} : null,
    routable: Boolean(state.selected_model), groups, failures: [], status: state.pending.includes('select_model') ? 'selecting' : 'ready', pending: null, error: null};
  if (JSON.stringify(modelDirectory.getSnapshot()) !== JSON.stringify(next)) modelDirectory.set(next);
  const catalog = {value: state.permission_modes?.length ? {options: state.permission_modes.map(option => ({value: permissionViewId(option.id), name: option.label, description: option.description}))} : null};
  if (JSON.stringify(permissionCatalog.getSnapshot()) !== JSON.stringify(catalog)) permissionCatalog.set(catalog);
});

export function Composer({owner = {}}: {owner?: any}) {
  const state = useSource(wire); const flag = useSource(attachmentFlag);
  const selectModel = async (selection: any) => {
    try { await action('select_model', {model_id: selection.model, ...(selection.reasoningEffort ? {reasoning_effort: selection.reasoningEffort} : {})}); return {ok: true, value: undefined}; }
    catch (error) { return {ok: false, error: {message: error instanceof Error ? error.message : 'Model selection failed.'}}; }
  };
  const renderComposerSlot = (slot: string, owner: any) => {
    if (slot === 'conversation.input.overlay') return <><MenuView menu={triggers!.menu} headers={triggers!.headers} onPick={(...args: any[]) => (triggers!.pick as any)(...args)} onCrumb={(...args: any[]) => (triggers!.pickCrumb as any)(...args)} onHover={(...args: any[]) => (triggers!.hover as any)(...args)} onDismiss={() => triggers!.dismiss()} t={triggerT as any}/><PopupSelectView popup={popup} t={commandT as any}/></>;
    if (slot === 'conversation.input.attachments') return <ComposerAttachments {...owner} canAcceptDrop={Boolean(state.capabilities?.can_upload_attachments) && owner.canAcceptDrop} t={t}/>;
    if (slot === 'conversation.input.model' && state.capabilities?.can_select_model && state.models.length) return <ModelSelect available directory={modelDirectory} load={() => {}} select={selectModel} locked={owner.locked || state.busy} t={modelT}/>;
    if (slot === 'conversation.input.permission' && state.capabilities?.can_set_permission_mode && state.permission_modes?.length) return <PermissionSelect locked={owner.locked || state.busy} usePermissionCatalog={(select: any) => useSource(permissionCatalog, select)} useProjection={useProjection} select={async (permission_mode: string) => { try { await action('set_permission_mode', {permission_mode: permissionWireId(permission_mode)}); return true; } catch (_) { return false; } }} t={permissionT}/>;
    return null;
  };
  const file = state.context.filepath?.split(/[\\/]/).pop() || 'Unsaved scene';
  const context = [file, state.context.active_object?.name, (state.context.selected_objects?.length || 0) > 1 ? `${state.context.selected_objects!.length} selected` : ''].filter(Boolean).join(' · ');
  return <div className="composer-seat">
    <GoalDialog/>
    <InputBar {...({
      sessionId: state.thread_id || 'unconnected', variant: 'composer', useSession,
      useInput: (select: any) => useSource(input, select), keyboard,
      inputActions: {pruneAttachments: (ids: string[]) => input.set({...input.getSnapshot(), attachmentIds: ids})},
      addFiles: state.capabilities?.can_upload_attachments ? addFiles : undefined, removeAttachment,
      resolveDraftAttachments: (ids: string[]) => ids.map(id => attachments.get(id)).filter(Boolean),
      retryFileUpload: (id: string) => safely(uploadOne(id, attachments.get(id).file)),
      toggleCommandMenu: (span: any) => triggers!.toggleSource('command', {trigger: '/', query: '', quoted: false, position: 'leading', span: {...span, draftRev: input.getSnapshot().draftRev}}),
      stop: () => safely(action('stop')), t, renderSlot: renderComposerSlot,
      useBusyEnter: (select: any) => select('queue'), useFileUploads: (select: any) => useSource(uploads, select),
      useNotices: (select: any) => useSource(notices, select), useLexicon: () => emptyLexicon,
      useMenuLauncher: (select: any) => useSource(triggers!.launcher, select), useStopShortcut: (select: any) => select([]),
      useProjection, useExcelSelection: () => undefined, showContextMeter: false,
      blocked: state.busy ? {kind: 'running'} : undefined,
      placeholder: state.ready ? 'Message Codex…' : 'Connect using your existing Codex login',
      ...owner, disabled: !state.ready || owner.disabled,
      accessory: flag ? <Button variant="ghost" onClick={() => { includeView = false; attachmentFlag.set(false); }}>Ansicht beim Senden anhängen ×</Button> : undefined,
    } as React.ComponentProps<typeof InputBar>)}/>
  </div>;
}
