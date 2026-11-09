import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Button, Modal, CodeBlock, FileTypeIcon} from '@deepseek-ai/dsh-client-ui-primitives';
import {installDeepblickTheme} from '../vendor/deepblick/packages/client/ui-brand-deepblick/src/client/theme';
import {installDeepblickLook} from '../vendor/deepblick/packages/client/ui-brand-deepblick/src/client/look';
import {ProductionShell} from './shell';
import {BoundConversationContent} from './conversation';
import {GeneratedImageInteraction, ImageAnnotationSurface} from './image-annotation';
import {ApprovalSeat} from './approval';
import {MessageImages} from '../vendor/deepblick/packages/client/ui-attachment/src/client/MessageImages';
import {t, setResourceOpener} from './project';
import {action, safely, wire, useSource, surface, startPolling, resourceBlob, loadImage, download, showError, type Resource} from './bridge';
import '../vendor/deepblick/packages/client/ui-theme/src/styles/design-platform.css';
import '../vendor/deepblick/packages/client/ui-theme/src/styles/base.css';
import '../vendor/deepblick/packages/client/ui-theme/src/styles/gradient-shadow-text.css';
import '../vendor/deepblick/packages/client/ui-theme/src/styles/focus.css';
import '../vendor/deepblick/packages/client/ui-theme/src/styles/scrollbar.css';
import '../vendor/deepblick/packages/client/ui-theme/src/styles/shiki.css';
import './shell.css';

// The original brand plugin's view-only effect seam, without a Cordis Host or
// account/provider runtime. Palette/fonts remain the actual source; the hero
// artwork is supplied by the Blender adapter.
installDeepblickTheme({effect: (effect: () => unknown) => effect(), theme: {overrideTokens: (_name: string, palette: Record<string, {light: string}>) => {
  for (const [name, value] of Object.entries(palette)) document.body.style.setProperty(name, value.light);
  return () => {};
}}} as Parameters<typeof installDeepblickTheme>[0]);
installDeepblickLook({effect: (effect: () => unknown) => effect()} as Parameters<typeof installDeepblickLook>[0]);

function ResourceLink({resource}: {resource: Resource}) {
  return <button className="resource-link" onClick={() => safely(openResource(resource))} title={resource.name}>
    <FileTypeIcon path={resource.name}/><span>{resource.name}</span><small>{resource.mime_type}</small>
  </button>;
}
let openResource: (resource: Resource) => Promise<void> = async () => {};
function ResourcePreview() {
  const [resource, setResource] = useState<Resource | null>(null);
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [image, setImage] = useState<string>();
  useEffect(() => {
    openResource = async value => { setResource(value); };
    setResourceOpener(openResource);
  }, []);
  useEffect(() => {
    let current = true;
    setText(''); setError(''); setImage(undefined);
    if (!resource) return;
    const image = resource.mime_type.startsWith('image/') && resource.mime_type !== 'image/svg+xml';
    const text = resource.mime_type.startsWith('text/') || ['application/json', 'application/xml'].includes(resource.mime_type);
    if (!image && !text) return;
    setLoading(true);
    const operation = image ? loadImage(resource).then(url => { if (current) setImage(url); })
      : resourceBlob(resource).then(async blob => {
        if (blob.size > 2 * 1024 * 1024) throw new Error('Text preview is limited to 2 MiB. Download the original file.');
        const content = await blob.text(); if (current) setText(content);
      });
    operation.catch(error => { if (current) setError(error.message); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [resource]);
  return <Modal open={Boolean(resource)} onClose={() => setResource(null)} title={resource?.name || 'File'} closeLabel="Close preview" footer={resource && <Button variant="primary" onClick={() => safely(download(resource))}>Download original</Button>}>
    {loading ? <p>Loading authenticated file…</p> : error ? <p role="alert">{error}</p> : image ? <GeneratedImageInteraction images={resource ? [{url: image, resource}] : []}><MessageImages images={[{preview: {url: image, name: resource?.name}}]} loadImage={loadImage} align="start" t={t}/></GeneratedImageInteraction>
      : text ? <CodeBlock code={text} lang="text" copyLabel="Copy" copiedLabel="Copied"/>
        : <p>This format has no preview in the Blender integration. Download the original file to open it in a supported application.</p>}
  </Modal>;
}
function Settings({close}: {close: () => void}) {
  const state = useSource(wire);
  const [values, setValues] = useState(() => ({codex_path: state.settings.codex_path || 'codex', mcp_command: state.settings.mcp_command || '', mcp_args: Array.isArray(state.settings.mcp_args) ? JSON.stringify(state.settings.mcp_args) : state.settings.mcp_args || '[]'}));
  const [error, setError] = useState('');
  return <Modal open onClose={close} title="Connection settings" closeLabel="Close settings" description="Codex connects automatically using your existing login. Saving settings reconnects automatically when idle." footer={<Button variant="primary" disabled={state.busy || state.pending.includes('settings') || !state.connected} onClick={() => {
    try {
      const args = JSON.parse(values.mcp_args);
      if (!Array.isArray(args) || args.some(arg => typeof arg !== 'string')) throw new Error('MCP arguments must be a JSON string array.');
      safely(action('settings', values).then(close));
    } catch (error) { setError((error as Error).message); }
  }}>Save settings</Button>}>
    {state.busy && <p role="status">Finish or stop the current response before saving connection settings.</p>}
    <div className="settings-fields">{Object.entries(values).map(([key, value]) => <label key={key}>{key.replaceAll('_', ' ')}<input value={value} onChange={event => setValues({...values, [key]: event.target.value})}/></label>)}</div>
    {error && <p role="alert">{error}</p>}
    <Button variant="outline" onClick={() => safely(action('provider_settings').then(close))}>Separate 3D provider settings</Button>
  </Modal>;
}
function Chat() {
  const state = useSource(wire);
  const [settings, setSettings] = useState(false);
  return <div className="blender-chat">
    <ProductionShell settings={() => setSettings(true)}>{owner => <BoundConversationContent owner={owner} dock={<>
      {(state.ui_error || state.error) && <div role="alert" className="bridge-error">{state.ui_error || state.error}</div>}
      {state.activity && <div className="bridge-activity" role="status">{state.activity}</div>}
      {state.artifacts?.length > 0 && <div className="artifact-rail" aria-label="Output files">{state.artifacts.map(resource => <ResourceLink key={resource.id} resource={resource}/>)}</div>}
      </>} approvals={state.approvals.length ? state.approvals.map(approval => <ApprovalSeat key={JSON.stringify(approval.request_id)} approval={approval}/>) : null}
      footer={<footer className="bridge-status" role="status"><span>{state.connected ? state.status : 'Waiting for Blender bridge'}</span></footer>}/>}</ProductionShell>
    {settings && <Settings close={() => setSettings(false)}/>}
    <ResourcePreview/>
  </div>;
}
class ErrorBoundary extends React.Component<{children: React.ReactNode}, {error: string}> {
  state = {error: ''};
  static getDerivedStateFromError(error: Error) { return {error: error.message}; }
  render() { return this.state.error ? <div className="bridge-error" role="alert">The chat UI could not render: {this.state.error}</div> : this.props.children; }
}
createRoot(document.getElementById('root')!).render(<ErrorBoundary>{surface === 'markup' ? null : surface === 'image-editor' ? <ImageAnnotationSurface/> : <Chat/>}</ErrorBoundary>);
startPolling();
