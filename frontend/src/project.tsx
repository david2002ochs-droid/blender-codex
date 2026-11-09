import React, {useCallback, useEffect, useState} from 'react';
import {createSnapshotStore} from '@deepseek-ai/dsh-client-store';
import {PartialArguments} from '@deepseek-ai/dsh-util-values';
import {TextShimmer} from '@deepseek-ai/dsh-client-ui-primitives';
import {ChatView} from '../vendor/deepblick/packages/client/ui-chat/src/client/chat/ChatView';
import {UserMessageNodeView} from '../vendor/deepblick/packages/client/ui-chat/src/client/chat/MessageItem';
import {AssistantNodeView} from '../vendor/deepblick/packages/client/ui-chat/src/client/chat/AssistantNodeView';
import {TurnProcessNodeView} from '../vendor/deepblick/packages/client/ui-chat/src/client/chat/TurnProcessNodeView';
import {presentationPolicyFor} from '../vendor/deepblick/packages/client/ui-chat/src/client/presentation-policy';
import {ToolCallTree} from '../vendor/deepblick/packages/client/ui-tool/src/client/tool/ToolCallTree';
import {MessageImages} from '../vendor/deepblick/packages/client/ui-attachment/src/client/MessageImages';
import {DeepblickThinkingEye} from '../vendor/deepblick/packages/client/ui-brand-deepblick/src/client/Brand';
import {en as chatLocale} from '../vendor/deepblick/packages/client/ui-chat/src/client/locale';
import {en as conversationLocale} from '../vendor/deepblick/packages/client/ui-conversation/src/client/locales';
import {en as approvalLocale} from '../vendor/deepblick/packages/client/ui-approval/src/client/locales';
import {en as modelLocale} from '../vendor/deepblick/packages/client/ui-model-selection/src/client/locales';
import {accessEn as permissionLocale} from '../vendor/deepblick/packages/client/ui-permission-presets/src/client/locales';
import {wire, useSource, resourceById, loadImage, showError, type Resource, type State, type WireTool} from './bridge';
import {GeneratedImageInteraction} from './image-annotation';
import {ImageGenerationStatus, isImageGeneration} from './image-generation';

const dictionaries = {...conversationLocale, ...chatLocale, ...approvalLocale};
export function translate(dictionary: Record<string, unknown>) {
  return (key: string, params?: Record<string, unknown>) => {
    const value = dictionary[key];
    if (typeof value !== 'string') return key;
    return value.replace(/\{(\w+)\}/g, (_, name) => String(params?.[name] ?? ''));
  };
}
export const t = translate(dictionaries);
export const modelT = translate(modelLocale);
export const permissionT = translate(permissionLocale);
export const permissionViewId = (mode: string) => mode === 'full_access' ? 'full-access' : mode === 'read_only' ? 'read-only' : mode;
export const permissionWireId = (mode: string) => mode === 'full-access' ? 'full_access' : mode === 'read-only' ? 'read_only' : mode;
const empty = Object.freeze([]);
const nodeSources = new Map<string, ReturnType<typeof createSnapshotStore<any>>>();
function source(key: string) {
  let value = nodeSources.get(key);
  if (!value) { value = createSnapshotStore(undefined); nodeSources.set(key, value); }
  return value;
}
export const nodeStore = {get: (key: string) => source(key).getSnapshot(), source, values: () => [...nodeSources.values()].map(store => store.getSnapshot()).filter(Boolean)};
const navigation = {items: () => empty};
const chatStore = createSnapshotStore({order: [] as string[], nodes: nodeStore, navigation});
const sessionStore = createSnapshotStore<any>({running: false, openState: 'open', openError: null, hasMore: false, loadingOlder: false, pendingSubmissions: [], subagent: null, promptError: null, removed: false});
// Preserve the latest UI's unfolded work details using Deepblick's real policy.
const presentation = presentationPolicyFor('verbose');
export const usePresentation = (select = (value: any) => value) => select(presentation);
export function useDisclosure() {
  const [expanded, setExpanded] = useState(false);
  const toggle = useCallback(() => setExpanded(value => !value), []);
  return {expanded, setExpanded, toggle};
}
export function useProjection(key: string, select = (value: any) => value) {
  const state = useSource(wire);
  return select(key === 'permissions' && state.permission_mode ? {currentValue: permissionViewId(state.permission_mode)} : undefined);
}
export const useSession = (select = (value: any) => value) => useSource(sessionStore, select);
export const useConversationSnapshot = () => {
  const state = useSource(wire);
  return {views: {grouped: () => undefined}, activeTargets: new Set(state.messages.length || state.tool_calls.length || state.reasoning?.length ? ['chat'] : [])};
};
const useChat = (select = (value: any) => value) => useSource(chatStore, select);
const useChatNode = (key: string, select = (value: any) => value) => useSource(source(key), select);
const noopHook = () => undefined;
const emptyConversation = {views: {grouped: () => undefined}};
const useConversation = (select: (value: any) => any) => select(emptyConversation);
const viewStore = {turnProcesses: []};
const useStore = (select: (value: any) => any) => select(viewStore);
export const useSessions = (select: (value: any) => any) => {
  const state = useSource(wire);
  const time = (value?: string | number) => typeof value === 'number' ? value * 1000 : Date.parse(value || '') || 0;
  const summaries = (state.threads || []).map(thread => ({id: thread.id, title: thread.title, displayTitle: thread.title,
    cwd: thread.project || '', createdAt: time(thread.created_at), updatedAt: time(thread.updated_at),
    origin: 'user', retainedBy: {mainView: thread.id === (state.active_thread_id || state.thread_id) ? 1 : 0}, blank: thread.id === state.thread_id && state.messages.length === 0 && state.tool_calls.length === 0 && !state.reasoning?.length}));
  if (state.thread_id && !summaries.some(row => row.id === state.thread_id)) summaries.push({id: state.thread_id, title: state.messages.find(message => ['you', 'user'].includes(message.role.toLowerCase()))?.text.slice(0, 80) || 'New chat', displayTitle: 'Current chat', cwd: state.context.filepath?.replace(/[\\/][^\\/]*$/, '') || '', retainedBy: {mainView: 1}, blank: state.messages.length === 0, origin: 'user', createdAt: 0, updatedAt: 0});
  return select({byId: Object.fromEntries(summaries.map(row => [row.id, row])), ids: summaries.map(row => row.id), projectionsBySession: {}, phase: state.history_loading ? 'loading' : 'ready', error: state.history_error || null});
};
const locations = {kind: 'session'};
function json(value: unknown) { return typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2); }
function toolBlock(tool: WireTool, children: WireTool[], all: WireTool[], visiting = new Set<string>()): any {
  visiting.add(tool.id);
  const argsRaw = json(tool.arguments);
  const base = {callId: tool.id, name: tool.tool_name, args: PartialArguments.fromText(argsRaw), argsRaw,
    time: tool.time, subCalls: children.filter(child => !visiting.has(child.id)).map(child => toolBlock(child, all.filter(item => item.parent_id === child.id), all, new Set(visiting)))};
  if (tool.status === 'running' || tool.status === 'preparing' || tool.status === 'inProgress') return {...base, phase: tool.status === 'preparing' ? 'preparing' : 'start'};
  let content = tool.content ?? tool.result;
  if (!Array.isArray(content)) content = [{type: 'text', text: json(content)}];
  const mapped = (content as any[]).map(block => block?.type === 'text' ? block
    : block?.resource_id && resourceById(block.resource_id) ? {type: block.type, attachment: resourceById(block.resource_id)}
      : {type: 'text', text: json(block)});
  if (tool.error) mapped.push({type: 'text', text: json(tool.error)});
  return {...base, kind: 'tool-result', call: {name: tool.tool_name, argsRaw}, callTime: tool.time ?? null,
    ...(tool.status === 'interrupted' ? {error: {name: 'ToolError', code: 'interrupted'}} : {}),
    content: mapped, isError: tool.status === 'failed' || Boolean(tool.error)};
}
let lastThread: string | undefined;
export function project(state: State) {
  if (state.thread_id !== lastThread) { for (const store of nodeSources.values()) store.set(undefined); lastThread = state.thread_id; }
  const entries: {key: string; seq?: number; kind: string; data: any}[] = [];
  for (const message of state.messages) {
    if (typeof message.id !== 'string' || !message.id) continue; // Never fabricate wire identities.
    const attachments = (message.attachments || []).map(item => typeof item === 'string' ? resourceById(item) : item).filter(Boolean) as Resource[];
    const user = ['you', 'user'].includes(message.role.toLowerCase());
    if (user) {
      const content: any[] = [{type: 'text', text: message.text || ''}];
      for (const resource of attachments) content.push({type: resource.mime_type.startsWith('image/') ? 'image' : 'file', attachment: {...resource, attachmentId: resource.id, bytes: resource.size}});
      entries.push({key: message.id, seq: message.seq ?? message.order ?? message.event_index, kind: 'user', data: {content, time: message.time}});
    } else {
      const blocks: any[] = [{kind: 'text', text: message.text || ''}];
      for (const resource of attachments) if (resource.mime_type.startsWith('image/')) blocks.push({kind: 'image', attachment: resource});
      entries.push({key: message.id, seq: message.seq ?? message.order ?? message.event_index, kind: 'assistant-step', data: {
        blocks, status: state.busy && message === state.messages.at(-1) ? 'running' : 'settled', step: 0,
      }});
    }
  }
  const tools = state.tool_calls || [];
  const seenTurns = new Set<string>();
  for (const row of state.reasoning || []) {
    if (!row.id || !row.item_id || !row.turn_id || row.thread_id !== state.thread_id) continue;
    const turnKey = JSON.stringify([row.thread_id, row.turn_id]);
    if (!seenTurns.has(turnKey) && ['completed', 'failed', 'interrupted'].includes(row.turn_status)) {
      seenTurns.add(turnKey);
      entries.push({key: 'turn-process:' + turnKey, seq: row.seq - 0.25, kind: 'codex-turn-status', data: row});
    }
    entries.push({key: 'reasoning:' + row.id, seq: row.seq, kind: 'assistant-step', data: {
      blocks: [{kind: 'reasoning', text: row.text}], status: row.status === 'running' && state.busy ? 'running' : row.status === 'interrupted' ? 'interrupted' : 'settled',
      step: 0, reasoningPreview: row.truncated,
    }});
  }
  for (const tool of tools) {
    if (!tool.id || (tool.parent_id && tools.some(parent => parent.id === tool.parent_id))) continue;
    entries.push({key: tool.id, seq: tool.seq ?? tool.order ?? tool.event_index, kind: 'tool', data: {root: toolBlock(tool, tools.filter(child => child.parent_id === tool.id), tools), progress: tool.progress, running: tool.status === 'running', generation: isImageGeneration(tool) ? {status: tool.status, error: tool.error} : undefined}});
  }
  // anchorSeq is a presentation position where Codex does not supply seq;
  // it is never represented as a durable Harness event/log sequence.
  entries.sort((a, b) => (a.seq ?? Number.MAX_SAFE_INTEGER) - (b.seq ?? Number.MAX_SAFE_INTEGER));
  const order = entries.map((entry, position) => {
    const node = {...entry, id: entry.key, anchorSeq: entry.seq ?? position, target: 'chat', visibility: 'visible', location: locations};
    const store = source(entry.key);
    if (JSON.stringify(store.getSnapshot()) !== JSON.stringify(node)) store.set(node);
    return entry.key;
  });
  const retained = new Set(order);
  for (const [key, store] of nodeSources) if (!retained.has(key)) { store.set(undefined); nodeSources.delete(key); }
  if (JSON.stringify(chatStore.getSnapshot().order) !== JSON.stringify(order)) chatStore.set({order, nodes: nodeStore, navigation});
  const nextSession = {...sessionStore.getSnapshot(), running: state.busy, blank: state.messages.length === 0 && state.tool_calls.length === 0 && !state.reasoning?.length, awaitingFirstTurn: false, promptAttempted: state.messages.length > 0};
  if (JSON.stringify(nextSession) !== JSON.stringify(sessionStore.getSnapshot())) sessionStore.set(nextSession);
}
wire.subscribe(() => project(wire.getSnapshot()));
project(wire.getSnapshot());

export let openResource: (resource: Resource) => Promise<void> = async () => { throw new Error('Resource preview is not mounted.'); };
export const setResourceOpener = (callback: typeof openResource) => { openResource = callback; };
export async function openFile(idOrName: string) {
  const state = wire.getSnapshot();
  const resource = resourceById(idOrName) || [...state.artifacts, ...state.attachments].find(item => item.name === idOrName);
  if (!resource) throw new Error('This file was not returned as an authorized artifact.');
  return openResource(resource);
}
const openExternalLink = (value: string) => {
  const url = new URL(value); if (!['http:', 'https:'].includes(url.protocol)) return;
  window.open(url.href, '_blank', 'noopener,noreferrer');
};
export function renderSlot(slot: string, owner: any, options?: any): React.ReactNode {
  if (slot === 'conversation.chat.node') {
    if (owner.node.kind === 'user') return <UserMessageNodeView {...owner} t={t}/>;
    if (owner.node.kind === 'assistant-step') return <><AssistantNodeView {...owner} useDisclosure={useDisclosure} useTurnData={noopHook} useStepData={noopHook} cellCitations={noopHook} usePresentation={usePresentation} t={t}/>{owner.node.data.reasoningPreview && <div className="bridge-activity" role="note">Summary preview truncated at the local display limit.</div>}</>;
    if (owner.node.kind === 'codex-turn-status') {
      const row = owner.node.data;
      const reason = row.turn_status === 'failed' ? 'error' : row.turn_status === 'interrupted' ? 'aborted' : 'completed';
      const turn: any = {turn: row.turn_id, status: 'closed', end: {data: {reason: {kind: reason}}}};
      if (Number.isFinite(row.started_at) && (Number.isFinite(row.completed_at) || Number.isFinite(row.duration_ms))) {
        turn.start = {time: row.started_at * 1000};
        turn.end.time = Number.isFinite(row.duration_ms) ? turn.start.time + row.duration_ms : row.completed_at * 1000;
      }
      return <TurnProcessNodeView {...owner} node={{...owner.node, kind: 'turn-process', location: {kind: 'turn', turn}, data: {turn: row.turn_id}}}
        turnProcess={{hasContent: true, foldable: false, open: true, setOpen() {}, spec: {} as any}} t={t}/>;
    }
    if (owner.node.kind === 'tool') {
      const images = (owner.node.data.root.content || []).filter((block: any) => block.type === 'image' && block.attachment).map((block: any) => ({attachment: block.attachment}));
      const progress = owner.node.data.progress?.at(-1);
      return <>{owner.node.data.generation && <ImageGenerationStatus tool={owner.node.data.generation} hasImage={images.length > 0}/>}<ToolCallTree {...owner} useDisclosure={useDisclosure} useHostInfo={(select: any) => select({})} renderSlot={renderSlot} t={t}/>{progress && <div className="bridge-activity"><TextShimmer active={owner.node.data.running}>{typeof progress === 'string' ? progress : json(progress)}</TextShimmer></div>}{images.length > 0 && <AuthenticatedImages images={images} align="start"/>}</>;
    }
  }
  if (slot === 'conversation.message.images' || slot === 'tool.call.images') return <AuthenticatedImages {...owner}/>;
  if (slot === 'conversation.chat.running.icon') return <DeepblickThinkingEye/>;
  return options?.fallback ?? null;
}
function AuthenticatedImages(owner: any) {
  const images = owner.images || [];
  const [resolved, setResolved] = useState<any[]>([]);
  const [error, setError] = useState('');
  const identity = JSON.stringify(images);
  useEffect(() => {
    let active = true;
    Promise.all(images.map(async (image: any) => {
      if (image.preview) return image;
      const reference = image.attachment;
      const id = reference?.id || reference?.attachmentId;
      if (!id) throw new Error('Image has no registered resource identity.');
      const descriptor = resourceById(id);
      const url = await loadImage({id});
      return {preview: {url, name: descriptor?.name}, resource: descriptor};
    })).then(values => { if (active) { setResolved(values); setError(''); } }, error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [identity]);
  const state = useSource(wire);
  const generated = resolved.filter(image => image.resource && state.artifacts.some(resource => resource.id === image.resource.id)).map(image => ({url: image.preview.url, resource: image.resource}));
  return error ? <div role="alert">{error}</div> : resolved.length ? <GeneratedImageInteraction images={generated}><MessageImages {...owner} images={resolved} loadImage={loadImage} t={t}/></GeneratedImageInteraction> : <span>Loading authenticated image…</span>;
}
const chatScroll = {save: (_value: unknown) => {}, read: () => null};
const noHistoryPaging = () => {};
export function Transcript() {
  const state = useSource(wire);
  return <>{Boolean(state.reasoning_omitted) && <div className="bridge-activity" role="note">{state.reasoning_omitted} older summary previews omitted by the local display limit.</div>}<ChatView {...({useSession, useChat, useChatNode, useChatNodeProcess: noopHook, useChatGroup: noopHook,
    useConversation, useSessions, useStore, actions: {setTurnProcessOpen() {}}, renderSlot,
    sessionId: state.thread_id || 'unconnected', openFile, openSkill: () => showError(new Error('Skills are not exposed by this backend.')),
    openExternalLink, loadOlder: noHistoryPaging, loadThrough: async () => {}, loadImage,
    inspectCall: undefined, chatScroll, forkAt: undefined, fileMentions: noopHook, usePresentation, useProjection, t,
  } as React.ComponentProps<typeof ChatView>)}/></>;
}
