import React from 'react';
import {createSnapshotStore} from '@deepseek-ai/dsh-client-store';
import {Button} from '@deepseek-ai/dsh-client-ui-primitives';
import {AppFrame} from '../vendor/deepblick/packages/client/ui-layout/src/client/AppFrame';
import {createLayoutStore} from '../vendor/deepblick/packages/client/ui-layout/src/client/stores';
import {SidebarRoot} from '../vendor/deepblick/packages/client/ui-sidebar/src/client/SidebarRoot';
import {HeaderLeadingControls} from '../vendor/deepblick/packages/client/ui-sidebar/src/client/HeaderLeadingControls';
import {WorkspaceBrowser} from '../vendor/deepblick/packages/client/ui-workspace/src/client/rows/WorkspaceBrowser';
import {createWorkspaceViewStore} from '../vendor/deepblick/packages/client/ui-workspace/src/client/stores';
import {RenameSessionMenuItem, SessionRenameDialog} from '../vendor/deepblick/packages/client/ui-workspace/src/client/session-actions/RenameSession';
import {ConversationHeader} from '../vendor/deepblick/packages/client/ui-conversation/src/client/skeleton/ConversationHeader';
import {ConversationSessionHeader} from '../vendor/deepblick/packages/client/ui-conversation/src/client/skeleton/ConversationSession';
import {ConversationMainPanel} from '../vendor/deepblick/packages/client/ui-conversation/src/client/skeleton/ConversationMainPanel';
import {DeepblickMark, DeepblickName} from '../vendor/deepblick/packages/client/ui-brand-deepblick/src/client/Brand';
import {en as sidebarLocale} from '../vendor/deepblick/packages/client/ui-sidebar/src/client/locales';
import {en as workspaceLocale} from '../vendor/deepblick/packages/client/ui-workspace/src/client/locales';
import {translate, useSessions, useSession, useConversationSnapshot, t} from './project';
import {action, safely, showError, useSource, wire} from './bridge';

const layout = createLayoutStore().create();
const workspace = createWorkspaceViewStore().create();
workspace.actions.setGroupBy('flat');
const rename = createSnapshotStore<any>(null);
const search = createSnapshotStore({addRequested: false, searchRequest: 0, forkError: null});
const empty: any[] = [];
const workspaces = {items: empty, phase: 'ready', state: 'ready', archivedSessionIds: empty, pinnedSessionIds: empty};
const sidebarT = translate(sidebarLocale), workspaceT = translate(workspaceLocale);
const shortcuts = (select: any) => select(empty);
const usePanelInfo = (select: any) => useSource(layout, value => select(value.panelInfo));
const useConversation = (select: any) => select(useConversationSnapshot());
const requestSessionRename = (sessionId: string, currentTitle: string) => rename.set({sessionId, currentTitle});
function collapseNarrow() {
  const info = layout.getSnapshot().layoutInfo;
  if (info.viewportWidth < 900 && info.narrowExpanded) layout.actions.toggleSidebar();
}
function startSession() {
  const state = wire.getSnapshot();
  // App Server connection itself creates the initial authoritative thread.
  // A New gesture during that handshake must not race a second thread/start.
  if (!state.ready || state.pending.includes('connect')) return;
  if (state.busy || state.history_loading) { showError(new Error('Finish or stop the current turn before switching chats.')); return; }
  safely(action(state.capabilities?.history ? 'threads/new' : 'new_chat').then(collapseNarrow));
}
function open(thread_id: string) {
  const state = wire.getSnapshot();
  if (thread_id === state.thread_id) { collapseNarrow(); return; }
  if (state.busy || state.history_loading) { showError(new Error('Finish or stop the current turn before switching chats.')); return; }
  safely(action('threads/open', {thread_id}).then(collapseNarrow));
}
const unavailable = () => { throw new Error('This Blender bridge does not provide workspace management.'); };
function History(props: any) {
  const state = useSource(wire);
  return <WorkspaceBrowser {...props} {...({
    usePanelInfo, useSessions,
    useSessionStatus: (select: any) => select(new Map(state.thread_id ? [[state.thread_id, {running: state.busy, pendingInteraction: state.approvals.length ? {kind: 'approval'} : undefined}]] : [])),
    useWorkspaces: (select: any) => select(workspaces), useStore: (select: any) => useSource(workspace, select), actions: workspace.actions,
    startSession, open, requestSessionRename, notifyArchivedNotOpenable: unavailable,
    renameWorkspace: unavailable, deleteWorkspace: unavailable, insertWorkspaceBefore: unavailable, unarchiveSession: unavailable, createWorkspace: unavailable,
    // The original browser merges actual indexed title matches itself. No
    // content-search endpoint exists, so this contributes no invented matches.
    searchSessions: async () => ({items: [], hasMore: false}), searchResultLimit: 100,
    useDirectoryFlow: (select: any) => select(false), useHostInfo: (select: any) => select({}), useShortcuts: shortcuts,
    useWorkspaceShortcuts: (select: any) => useSource(search, select),
    requestSearch: () => search.set({...search.getSnapshot(), searchRequest: search.getSnapshot().searchRequest + 1}),
    requestAddWorkspace: unavailable, closeAddWorkspace: () => search.set({...search.getSnapshot(), addRequested: false}), setDirectoryBusy: () => {}, dismissForkError: () => search.set({...search.getSnapshot(), forkError: null}),
    renderSlot: (slot: string, owner: any, options: any) => slot === 'sidebar.workspaces.session.menu.item'
      ? <RenameSessionMenuItem {...owner} useMenuOpenState={() => options.hookContext} useShortcuts={shortcuts} requestSessionRename={requestSessionRename} t={workspaceT}/>
      : null,
    t: workspaceT,
  } as any)}/>;
}
export function ProductionShell({children, settings}: {children: React.ReactNode | ((owner: any) => React.ReactNode); settings: () => void}) {
  const state = useSource(wire);
  const info = useSource(layout, value => value.layoutInfo);
  const collapsed = info.viewportWidth < 900 ? !info.narrowExpanded : info.sidebar === 0;
  const headerSlot = (slot: string, owner: any, options?: any): any => {
    if (slot === 'conversation.header.leading') return collapsed ? <HeaderLeadingControls {...({toggleSidebar: layout.actions.toggleSidebar, startSession, useShortcuts: shortcuts, t: sidebarT} as any)}/> : null;
    if (slot === 'conversation.session.header') return <ConversationSessionHeader {...owner} {...({sessionId: state.thread_id, useSessions, useConversationViews: (select: any) => select([{id: 'chat', label: 'Chat'}]), useStore: (select: any) => select({view: 'chat'}), renderSlot: headerSlot, open, selectView: () => {}, t} as any)}/>;
    if (slot === 'conversation.session.header.corner') return <Button variant="ghost" aria-label="Minimize chat" onClick={() => safely(action('hide_panel'))}>−</Button>;
    return options?.fallback || null;
  };
  const renderSlot = (slot: string, owner: any): any => {
    if (slot === 'sidebar') return <div className="production-sidebar" aria-hidden={collapsed || undefined} {...(collapsed ? {inert: ''} : {})}><SidebarRoot {...owner} {...({startSession, toggleSidebar: layout.actions.toggleSidebar, selectPanel: layout.actions.selectPanel, usePanels: (select: any) => select(empty), usePanelInfo, useShortcuts: shortcuts, t: sidebarT, renderSlot} as any)}/></div>;
    if (slot === 'sidebar.brand.mark') return <DeepblickMark size={25}/>;
    if (slot === 'sidebar.brand.name') return <DeepblickName t={() => 'Deepblick'}/>;
    if (slot === 'sidebar.workspaces') return <History {...owner}/>;
    if (slot === 'sidebar.settings') return <Button variant="ghost" aria-label="Settings" onClick={settings}>{owner.wide ? 'Settings' : '⋯'}</Button>;
    if (slot === 'main') return <ConversationMainPanel {...({sessionId: state.thread_id || undefined, useSession, useSessions, useConversation,
      renderSlot: () => <ConversationHeader {...({sessionId: state.thread_id || undefined, useSession, useConversation, renderSlot: headerSlot} as any)}/>,
      // The transport supplies a Blender project context rather than Harness
      // workspace IDs. Keep the real bound transcript/composer in this source
      // factory seat; do not fabricate a workspace to activate its hero picker.
      renderFactorySlot: (_slot: string, owner: any) => typeof children === 'function' ? children(owner) : <div className="blender-conversation-content">{children}</div>,
    } as any)}/>;
    if (slot === 'shell.overlay') return <SessionRenameDialog {...({useRenameRequest: (select: any) => useSource(rename, select), settleSessionRename: () => rename.set(null), renameSession: (thread_id: string, title: string) => action('threads/rename', {thread_id, title}), t: workspaceT} as any)}/>;
    return null;
  };
  return <div className="production-shell" data-sidebar-collapsed={collapsed}><AppFrame {...({useStore: (select: any) => useSource(layout, select), useSessions, usePanelInfo, actions: layout.actions, renderSlot, t} as any)}/></div>;
}
