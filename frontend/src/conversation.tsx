import React, {useContext, useMemo} from 'react';
import {createSnapshotStore} from '@deepseek-ai/dsh-client-store';
import {ConversationContent} from '../vendor/deepblick/packages/client/ui-conversation/src/client/skeleton/ConversationContent';
import {ConversationSession} from '../vendor/deepblick/packages/client/ui-conversation/src/client/skeleton/ConversationSession';
import {WorkspacePickFlow} from '../vendor/deepblick/packages/client/ui-workspace/src/client/WorkspacePicker';
import {BlenderHero} from './blender-hero';
import {en as workspaceLocale} from '../vendor/deepblick/packages/client/ui-workspace/src/client/locales';
import {Composer, useComposerInput, bindDraftPersistence, persistComposerDraft} from './composer';
import {Transcript, useSession, useSessions, useConversationSnapshot, t, translate} from './project';
import {wire, useSource} from './bridge';

const view = createSnapshotStore<any>({view: 'chat', viewRequest: null, draft: ''});
const viewActions = {setDraft: (draft: string) => view.set({...view.getSnapshot(), draft}), completeViewRequest: () => view.set({...view.getSnapshot(), viewRequest: null})};
const inputActions = {persistDraft: persistComposerDraft};
const workspaceT = translate(workspaceLocale);
const useConversation = (select: any) => select(useConversationSnapshot());
const SlotContext = React.createContext<any>(null);
function BoundViews() { return <Views renderSlot={useContext(SlotContext)}/>; }
function Views({renderSlot}: {renderSlot: any}) {
  return <ConversationSession {...({useSession, useConversation, useConversationViews: (select: any) => select([{id: 'chat', label: 'Chat'}]), inputActions,
    useStore: (select: any) => useSource(view, select), actions: viewActions, renderSlot, bindDraftPersistence,
    openView: (id: string) => { if (id === 'chat') view.set({...view.getSnapshot(), view: id}); }, useInspectCall: (select: any) => select(null),
  } as any)}/>;
}

/** The real production content/hero/composer geometry. Backend paths become
 * view-only project identities; no Harness workspace or remote ID is invented. */
export function BoundConversationContent({owner, dock, approvals, footer}: {owner: any; dock: React.ReactNode; approvals: React.ReactNode; footer: React.ReactNode}) {
  const state = useSource(wire);
  const project = state.project_root || state.threads?.find(thread => thread.id === state.thread_id)?.project
    || (/^(?:[a-z]:[\\/]|\/)/i.test(state.context.filepath || '') ? state.context.filepath!.replace(/[\\/][^\\/]*$/, '') : '');
  const workspaces = useMemo(() => ({phase: 'ready', state: 'ready', items: project && state.thread_id ? [{workspaceId: project, title: project.split(/[\\/]/).filter(Boolean).at(-1) || project, path: project, sessionIds: [state.thread_id]}] : [], archivedSessionIds: [], pinnedSessionIds: []}), [project, state.thread_id]);
  const useWorkspaces = (select: any) => select(workspaces);
  const slot = (name: string, props: any, options?: any): any => {
    if (name === 'conversation.session') return <Views renderSlot={slot}/>;
    if (name === 'conversation.view') return <Transcript/>;
    if (name === 'conversation.composer.bar') return <Composer owner={props}/>;
    if (name === 'conversation.input.dock') return dock;
    if (name === 'conversation.hero.brand.mark') return null;
    if (name === 'conversation.hero.brand.name') return <BlenderHero/>;
    if (name === 'conversation.hero.workspace') return <WorkspacePickFlow {...props} {...({t: workspaceT, useWorkspaces, createWorkspace: async () => { throw new Error('Project folders are managed by Blender.'); }, useDirectoryFlow: (select: any) => select(false), renderDirectoryFlow: () => null} as any)}/>;
    return options?.fallback || null;
  };
  return <SlotContext.Provider value={slot}><ConversationContent {...owner} {...({sessionId: state.thread_id || undefined, useSession, useSessions, useSessionStatus: (select: any) => select(new Map(state.thread_id ? [[state.thread_id, {running: state.busy, pendingInteraction: state.approvals.length ? {kind: 'approval'} : undefined}]] : [])),
    useWorkspaces, useInput: useComposerInput, useComposerBlock: (select: any) => select(undefined), renderSlot: slot,
    renderSlotChain: (_slot: string, _props: any, options: any) => approvals || options.fallback,
    selectWorkspace: async (id: string) => { if (id !== project) throw new Error('This is not the current Blender project.'); }, t,
    useFactorySlot: (name: string, fallback: any) => name === 'views' ? BoundViews : fallback,
  } as any)}/>{footer}</SlotContext.Provider>;
}
