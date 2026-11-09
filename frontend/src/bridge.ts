import {createSnapshotStore} from '@deepseek-ai/dsh-client-store';
import {useSyncExternalStore} from 'react';

export type Resource = {id: string; name: string; mime_type: string; size?: number; resource_url: string; width?: number; height?: number};
export type WireMessage = {id: string; role: string; text: string; turn_id?: string; seq?: number; order?: number; event_index?: number; time?: number; has_view?: boolean; attachments?: (string | Resource)[]};
export type WireTool = {id: string; tool_name: string; kind?: string; turn_id?: string; arguments?: unknown; status: string; content?: unknown; result?: unknown; error?: unknown; parent_id?: string; seq?: number; order?: number; event_index?: number; time?: number; progress?: unknown[]};
export type WireReasoning = {id: string; thread_id: string; turn_id: string; item_id: string; seq: number; text: string; status: string; turn_status: string; truncated?: boolean; started_at?: number; completed_at?: number; duration_ms?: number};
export type State = {
  thread_id?: string; ready: boolean; busy: boolean; status: string; error: string; activity: string;
  messages: WireMessage[]; tool_calls: WireTool[]; approvals: {request_id: string | number; text: string; tool_call_id?: string}[];
  reasoning?: WireReasoning[]; reasoning_omitted?: number;
  context: {filepath?: string; active_object?: {name: string}; selected_objects?: {name: string}[]};
  settings: {codex_path?: string; mcp_command?: string; mcp_args?: string | string[]};
  attachments: Resource[]; artifacts: Resource[]; models: Record<string, unknown>[];
  selected_model?: string; reasoning_effort?: string; permission_mode?: string;
  permission_modes?: {id: string; label: string; description?: string}[];
  ui_capture_surfaces?: {id: string; label: string}[];
  markup_active?: boolean;
  threads?: {id: string; title: string; created_at?: string | number; updated_at?: string | number; project?: string}[];
  active_thread_id?: string | null; history_loading?: boolean; history_error?: string;
  image_markup?: {active: boolean; id: string; thread_id: string; generation: number; resources: Resource[]; source_resource_id?: string} | null;
  collaboration_mode?: string; collaboration_modes?: any[]; goal?: {objective?: string; status?: string; tokenBudget?: number; token_budget?: number} | null; command_status?: Record<string, unknown>;
  project_root?: string;
  capabilities?: Record<string, boolean | number>; connected: boolean; pending: string[]; ui_error: string;
};
const initial: State = {ready: false, busy: false, status: 'Connecting to Blender…', error: '', activity: '', messages: [], tool_calls: [], approvals: [], context: {}, settings: {}, attachments: [], artifacts: [], models: [], connected: false, pending: [], ui_error: ''};
export const wire = createSnapshotStore<State>(initial);
export function useSource<T, U = T>(source: {subscribe: (fn: () => void) => () => void; getSnapshot: () => T}, select: (state: T) => U = value => value as unknown as U): U {
  return select(useSyncExternalStore(source.subscribe, source.getSnapshot, source.getSnapshot));
}
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get('token') || '';
export const surface = fragment.get('surface') === 'markup' ? 'markup' : fragment.get('surface') === 'image-editor' ? 'image-editor' : 'chat';
if (location.hash) history.replaceState(null, '', location.pathname + location.search);
const resources = new Map<string, Resource>();
const imageCache = new Map<string, Promise<string>>();
const cachedURLs = new Map<string, string>();
export const resourceById = (id: string) => resources.get(id);

export function showError(error: unknown) {
  wire.set({...wire.getSnapshot(), ui_error: error instanceof Error ? error.message : String(error)});
}
async function fetchLocal(url: string, init: RequestInit = {}) {
  const address = new URL(url, location.href);
  if (address.origin !== location.origin || !address.pathname.startsWith('/api/')) throw new Error('Resource is outside the authenticated Blender bridge.');
  if (!token) throw new Error('Reopen the chat from Blender to restore its local connection.');
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(address.href, {...init, cache: 'no-store', credentials: 'omit', signal: controller.signal, headers: {...init.headers, 'X-Codex-Token': token}});
    if (!response.ok) {
      let message = `Blender request failed (${response.status}).`;
      try { const body = await response.json(); if (typeof body.error === 'string') message = body.error; } catch (_) { /* No diagnostic body. */ }
      throw new Error(message);
    }
    return response;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('Blender did not respond. Check its window before repeating this action.');
    throw error;
  } finally { clearTimeout(timer); }
}
export async function action(name: string, values: Record<string, unknown> = {}) {
  if (wire.getSnapshot().pending.includes(name)) throw new Error('This action is already pending.');
  wire.set({...wire.getSnapshot(), pending: [...wire.getSnapshot().pending, name], ui_error: ''});
  try {
    const response = await fetchLocal('/api/action', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: name, ...values})});
    const result = await response.json();
    if (result.error || result.ok === false) throw new Error(String(result.error || 'Blender rejected this action.'));
    return result;
  } catch (error) { showError(error); throw error; }
  finally { wire.set({...wire.getSnapshot(), pending: wire.getSnapshot().pending.filter(item => item !== name)}); }
}
export const safely = (operation: Promise<unknown>) => { void operation.catch(() => {}); };

export async function resourceBlob(resource: Resource) {
  const response = await fetchLocal(resource.resource_url);
  return response.blob();
}
export const loadImage = Object.assign(async (attachment: {id: string}) => {
  const descriptor = resources.get(attachment.id);
  if (!descriptor) throw new Error('This image is not available in the current authenticated session.');
  let pending = imageCache.get(descriptor.id);
  if (!pending) {
    const thread = wire.getSnapshot().thread_id;
    pending = resourceBlob(descriptor).then(blob => {
      if (!blob.type.startsWith('image/') || blob.type === 'image/svg+xml') throw new Error('Unsupported image format; download the original file instead.');
      if (wire.getSnapshot().thread_id !== thread) throw new Error('The chat changed before this image finished loading.');
      const url = URL.createObjectURL(blob); cachedURLs.set(descriptor.id, url); return url;
    }).catch(error => { imageCache.delete(descriptor.id); throw error; });
    imageCache.set(descriptor.id, pending);
  }
  return pending;
}, {peek: (attachment: {id: string}) => cachedURLs.get(attachment.id)});

export async function download(resource: Resource) {
  const url = URL.createObjectURL(await resourceBlob(resource));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = resource.name || 'download'; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function upload(file: File): Promise<Resource> {
  if (!wire.getSnapshot().capabilities?.can_upload_attachments) throw new Error('This backend does not support file uploads.');
  const limit = Number(wire.getSnapshot().capabilities?.max_attachment_bytes || 20 * 1024 * 1024);
  if (file.size > limit) throw new Error(`File exceeds the supported ${(limit / 1024 / 1024).toFixed(0)} MiB limit.`);
  const base64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1] || ''); reader.onerror = () => reject(new Error('Cannot read selected file.')); reader.readAsDataURL(file);
  });
  const result = await action('upload_attachment', {name: file.name, mime_type: file.type || 'application/octet-stream', data_base64: base64});
  if (!result.attachment?.id) throw new Error('The backend did not return an attachment identity.');
  resources.set(result.attachment.id, result.attachment); return result.attachment;
}

let timer: ReturnType<typeof setTimeout>;
let polling = false;
export function startPolling() {
  document.addEventListener('keydown', event => {
    const state = wire.getSnapshot();
    if (event.key !== 'Escape' || event.isComposing || !state.markup_active) return;
    // Markup cancellation outranks menus/editor keymaps while actual markup
    // is active. It never clears drafts or maps Escape to agent interruption.
    event.preventDefault(); event.stopImmediatePropagation();
    if (!state.pending.includes('markup_cancel')) safely(action('markup_cancel'));
  }, true);
  async function poll() {
    if (document.hidden || polling) return;
    polling = true;
    try {
      const response = await fetchLocal('/api/state'); const next = await response.json();
      if (next.thread_id && wire.getSnapshot().thread_id && next.thread_id !== wire.getSnapshot().thread_id) {
        for (const url of cachedURLs.values()) URL.revokeObjectURL(url);
        resources.clear(); imageCache.clear(); cachedURLs.clear();
      }
      for (const resource of [...(next.attachments || []), ...(next.artifacts || []), ...(next.image_markup?.resources || [])]) if (resource?.id) resources.set(resource.id, resource);
      const previous = wire.getSnapshot();
      const normalized = {...initial, ...next, connected: true, pending: previous.pending, ui_error: previous.connected ? previous.ui_error : ''};
      if (JSON.stringify(normalized) !== JSON.stringify(previous)) wire.set(normalized);
    } catch (error) { wire.set({...wire.getSnapshot(), connected: false, ui_error: error instanceof Error ? error.message : 'Cannot reach Blender.'}); }
    finally { polling = false; timer = setTimeout(poll, 250); }
  }
  document.addEventListener('visibilitychange', () => { clearTimeout(timer); if (!document.hidden) void poll(); });
  window.addEventListener('pagehide', () => { clearTimeout(timer); for (const url of cachedURLs.values()) URL.revokeObjectURL(url); });
  void poll();
}
