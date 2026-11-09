import React, {useRef, useState} from 'react';
import {Button, Modal} from '@deepseek-ai/dsh-client-ui-primitives';
import {action, resourceBlob, useSource, wire, type Resource} from './bridge';
import {ScreenshotMarkupEditor, type MarkupSource, type MarkupResult, type FeedbackReceipt} from './markup-editor';

/** Session routing is an explicit injected capability, never guessed here. */
export function UIFeedback({onClose, onSubmit, targetLabel, initialSource}: {
  onClose: () => void; onSubmit?: (result: MarkupResult) => Promise<FeedbackReceipt | void>; targetLabel?: string; initialSource?: MarkupSource;
}) {
  const state = useSource(wire);
  const [source, setSource] = useState<MarkupSource | undefined>(initialSource);
  const [sourceGeneration, setSourceGeneration] = useState(0);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  function adoptSource(value: MarkupSource) { setSource(value); setSourceGeneration(value => value + 1); }
  async function capturedSource(surface: string): Promise<MarkupSource> {
    const result = await action('capture_ui', {surface});
    const resource = (result.resource || result.attachment) as Resource | undefined;
    if (!resource?.id || !resource.resource_url) throw new Error('Blender did not return an authenticated UI screenshot.');
    return {blob: await resourceBlob(resource), name: resource.name || 'ui-capture.png', surface};
  }
  async function capture(surface: string) {
    setCapturing(true); setError('');
    try {
      // Capture the real underlying surface, not this chooser/modal. Allow
      // two compositor frames after its removal before the native request.
      await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
      adoptSource(await capturedSource(surface));
    } catch (error) { setError((error as Error).message); }
    finally { setCapturing(false); }
  }
  async function prepareForDevelopment(result: MarkupResult): Promise<FeedbackReceipt> {
    const data_base64 = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('Cannot encode feedback PNG.')); reader.readAsDataURL(result.png); });
    const reply = await action('prepare_ui_feedback', {name: 'ui-feedback.png', comment: result.comment, source_surface: result.source, mime_type: 'image/png', data_base64});
    const receipt = reply.feedback;
    if (!receipt || !['prepared', 'adopted'].includes(receipt.status)) throw new Error('No development-feedback receipt was returned. Delivery is not confirmed.');
    return receipt;
  }
  if (capturing) return null;
  if (source) return <ScreenshotMarkupEditor key={sourceGeneration} source={source} onCancel={onClose}
    onSubmit={onSubmit || (state.capabilities?.can_prepare_ui_feedback ? prepareForDevelopment : undefined)} targetLabel={targetLabel || 'Entwicklung'}
    onCaptureCurrentUI={state.capabilities?.can_capture_ui ? async () => {
      // Keep this editor and its controls visible until native capture ends;
      // only then open a new editor over that frozen real-UI screenshot.
      const captured = await capturedSource('chat'); adoptSource({...captured, surface: 'editor'});
    } : undefined}/>;
  return <Modal open onClose={onClose} title="UI markieren" closeLabel="UI-Feedback schließen" description="Markiere die Chat-Oberfläche oder die Zeichenleiste, um Feedback zur Bedienoberfläche zu geben. Das ist kein Auftrag zur Änderung der Szene." footer={<Button variant="outline" onClick={onClose}>Abbrechen</Button>}>
    <div className="feedback-choices">
      {state.capabilities?.can_capture_ui && (state.ui_capture_surfaces || [{id: 'chat', label: 'Chat'}, {id: 'markup', label: 'Zeichenleiste'}]).map(surface => <Button key={surface.id} variant="outline" onClick={() => void capture(surface.id)}>{surface.label} aufnehmen</Button>)}
      <Button variant="outline" onClick={() => input.current?.click()}>Eigenes Bildschirmbild auswählen</Button>
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={event => {
        const file = event.target.files?.[0];
        if (file && ['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) setSource({blob: file, name: file.name, surface: 'file'});
        else if (file) setError('Bitte ein PNG-, JPEG- oder WebP-Bild wählen.');
      }}/>
    </div>
    {!state.capabilities?.can_capture_ui && <p className="markup-target-note">Direkte UI-Aufnahme ist mit diesem Backend noch nicht verfügbar. Ein ausgewähltes Bild bleibt bis zum ausdrücklichen Versand lokal.</p>}
    {state.capabilities?.can_capture_ui && <p className="markup-target-note">Ctrl + Alt + M nimmt die aktuelle Chat-Oberfläche einschließlich geöffneter Dialoge auf, bevor der Feedbackeditor erscheint.</p>}
    {error && <p className="bridge-error" role="alert">{error}</p>}
  </Modal>;
}
