import React, {useEffect, useRef, useState} from 'react';
import {Button, Modal} from '@deepseek-ai/dsh-client-ui-primitives';

export type MarkupSource = {blob: Blob; name: string; surface: string};
export type MarkupResult = {png: Blob; comment: string; source: MarkupSource['surface']};
export type FeedbackReceipt = {status: 'prepared' | 'adopted'; message?: string; id?: string};
export type Point = {x: number; y: number};
type Tool = 'pen' | 'rectangle' | 'arrow';
export type Mark = {tool: Tool; points: Point[]; color: string; width: number};

export function paint(context: CanvasRenderingContext2D, mark: Mark) {
  if (!mark.points.length) return;
  context.save(); context.lineWidth = mark.width; context.strokeStyle = mark.color;
  context.fillStyle = mark.color; context.lineCap = 'round'; context.lineJoin = 'round';
  const start = mark.points[0], end = mark.points.at(-1)!;
  context.beginPath();
  if (mark.tool === 'rectangle') context.strokeRect(start.x, start.y, end.x - start.x, end.y - start.y);
  else {
    context.moveTo(start.x, start.y);
    if (mark.tool === 'pen') for (const point of mark.points.slice(1)) context.lineTo(point.x, point.y);
    else context.lineTo(end.x, end.y);
    context.stroke();
    if (mark.tool === 'pen' && mark.points.length === 1) { context.beginPath(); context.arc(start.x, start.y, mark.width / 2, 0, Math.PI * 2); context.fill(); }
    if (mark.tool === 'arrow') {
      const angle = Math.atan2(end.y - start.y, end.x - start.x), length = Math.max(10, mark.width * 4);
      context.beginPath(); context.moveTo(end.x - length * Math.cos(angle - Math.PI / 6), end.y - length * Math.sin(angle - Math.PI / 6));
      context.lineTo(end.x, end.y); context.lineTo(end.x - length * Math.cos(angle + Math.PI / 6), end.y - length * Math.sin(angle + Math.PI / 6)); context.stroke();
    }
  }
  context.restore();
}

/** Original pixels are immutable; every mark exists only in the overlay model. */
export function ScreenshotMarkupEditor({source, onCancel, onSubmit, targetLabel, onCaptureCurrentUI}: {
  source: MarkupSource; onCancel: () => void;
  onSubmit?: (result: MarkupResult) => Promise<FeedbackReceipt | void>; targetLabel?: string;
  onCaptureCurrentUI?: () => Promise<void>;
}) {
  const [url] = useState(() => URL.createObjectURL(source.blob));
  const [size, setSize] = useState<{width: number; height: number}>();
  const [marks, setMarks] = useState<Mark[]>([]);
  const [draft, setDraft] = useState<Mark | null>(null);
  const [tool, setTool] = useState<Tool>('pen');
  const [color, setColor] = useState('#B0503C');
  const [comment, setComment] = useState('');
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState('');
  const image = useRef<HTMLImageElement>(null), canvas = useRef<HTMLCanvasElement>(null);
  const active = useRef<Mark | null>(null);
  const pointerId = useRef<number | null>(null);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => {
    const context = canvas.current?.getContext('2d');
    if (!context || !size) return;
    context.clearRect(0, 0, size.width, size.height);
    for (const mark of marks) paint(context, mark);
    if (draft) paint(context, draft);
  }, [marks, draft, size, preview]);
  function point(event: React.PointerEvent<HTMLCanvasElement>): Point {
    const rect = event.currentTarget.getBoundingClientRect();
    return {x: Math.max(0, Math.min(size!.width, (event.clientX - rect.left) * size!.width / rect.width)),
      y: Math.max(0, Math.min(size!.height, (event.clientY - rect.top) * size!.height / rect.height))};
  }
  function begin(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!size || preview || busy || event.button !== 0) return;
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); pointerId.current = event.pointerId;
    const mark = {tool, color, width: Math.max(2, Math.round(Math.min(size.width, size.height) / 150)), points: [point(event)]};
    active.current = mark; setDraft(mark);
  }
  function move(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!active.current || event.pointerId !== pointerId.current) return;
    const position = point(event), previous = active.current;
    const updated = {...previous, points: previous.tool === 'pen' ? [...previous.points, position] : [previous.points[0], position]};
    active.current = updated; setDraft(updated);
  }
  function end(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!active.current || event.pointerId !== pointerId.current) return;
    const mark = active.current; active.current = null; pointerId.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    setMarks(previous => [...previous, mark]); setDraft(null);
  }
  async function compose(): Promise<Blob> {
    if (!size || !image.current?.complete) throw new Error('Wait for the original screenshot to load.');
    const output = document.createElement('canvas'); output.width = size.width; output.height = size.height;
    const context = output.getContext('2d'); if (!context) throw new Error('PNG composition is unavailable.');
    context.drawImage(image.current, 0, 0);
    for (const mark of marks) paint(context, mark);
    return new Promise((resolve, reject) => output.toBlob(blob => blob ? resolve(blob) : reject(new Error('PNG export failed.')), 'image/png'));
  }
  async function showPreview() {
    if (preview) { setPreview(undefined); return; }
    try { setBusy(true); setPreview(URL.createObjectURL(await compose())); }
    catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  async function submit() {
    if (!onSubmit || !comment.trim() || busy) return;
    try {
      setBusy(true); setError('');
      const result = await onSubmit({png: await compose(), comment: comment.trim(), source: source.surface});
      setReceipt(result?.status === 'adopted' ? 'Von der Entwicklung übernommen.' : result?.status === 'prepared' ? 'Für die Entwicklung bereitgestellt. Noch nicht automatisch in dieser Codex-Session übernommen.' : 'Zur weiteren Verarbeitung übergeben; kein automatischer Empfang bestätigt.');
    }
    catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  async function exportFeedback() {
    try {
      setBusy(true); setError('');
      const png = await compose();
      const data = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('PNG could not be exported.')); reader.readAsDataURL(png); });
      const payload = {version: 1, kind: 'blender-ui-feedback', target: 'development', source_surface: source.surface, comment: comment.trim(), image: {mime_type: 'image/png', data_base64: data}};
      const address = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'}));
      const link = document.createElement('a'); link.href = address; link.download = 'blender-ui-feedback-' + Date.now() + '.json'; link.click();
      setTimeout(() => URL.revokeObjectURL(address), 1000);
      setReceipt('Export angefordert. Noch nicht an die Entwicklungssession übergeben oder von ihr übernommen.');
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  return <Modal open onClose={busy ? () => {} : onCancel} title="UI markieren" closeLabel="Markieren abbrechen" className="markup-editor-modal" footer={<div className="markup-editor-footer">
    <Button variant="outline" onClick={onCancel} disabled={busy}>Abbrechen</Button>
    <Button variant="outline" onClick={() => safelyPreview()} disabled={busy || !size}>{preview ? 'Weiter markieren' : 'Vorschau'}</Button>
    <Button variant="outline" onClick={() => void exportFeedback()} disabled={busy || !size || !comment.trim()}>Feedback exportieren</Button>
    {onSubmit && <Button variant="primary" onClick={() => void submit()} disabled={busy || !size || !comment.trim()}>Für {targetLabel || 'Entwicklung'} bereitstellen</Button>}
  </div>}>
    <div className="markup-editor-tools" role="toolbar" aria-label="Markierwerkzeuge">
      {(['pen', 'rectangle', 'arrow'] as Tool[]).map((value, index) => <Button key={value} variant={tool === value ? 'primary' : 'outline'} aria-pressed={tool === value} onClick={() => setTool(value)} disabled={busy || Boolean(preview)}>{['Stift', 'Rechteck', 'Pfeil'][index]}</Button>)}
      <label className="markup-color">Farbe <input type="color" aria-label="Markierungsfarbe" value={color} onChange={event => setColor(event.target.value)} disabled={busy || Boolean(preview)}/></label>
      <Button variant="ghost" disabled={!marks.length || busy || Boolean(preview)} onClick={() => setMarks(previous => previous.slice(0, -1))}>Rückgängig</Button>
      <Button variant="ghost" disabled={!marks.length || busy || Boolean(preview)} onClick={() => setMarks([])}>Eigene Markierungen leeren</Button>
      {onCaptureCurrentUI && <Button variant="ghost" disabled={busy} onClick={() => { void onCaptureCurrentUI().catch(error => setError(error.message)); }}>Diese Markierungsoberfläche kommentieren</Button>}
    </div>
    <div className="markup-image-scroll"><div className="markup-image-stage" data-mark-count={marks.length}>
      <img ref={image} src={url} alt="Unveränderte UI-Aufnahme" draggable={false} className={preview ? 'markup-original-hidden' : ''} onLoad={event => {
        const width = event.currentTarget.naturalWidth, height = event.currentTarget.naturalHeight;
        if (width * height > 24000000) { setError('The image exceeds the 24 megapixel editor limit.'); return; }
        setSize({width, height});
      }} onError={() => setError('The selected image could not be decoded.')}/>
      {size && !preview && <canvas ref={canvas} width={size.width} height={size.height} aria-label="Markierungsebene" onPointerDown={begin} onPointerMove={move} onPointerUp={end} onPointerCancel={() => { active.current = null; pointerId.current = null; setDraft(null); }}/>}
      {preview && <img src={preview} alt="PNG-Vorschau mit Markierungen" className="markup-preview-image"/>}
    </div></div>
    <label className="markup-comment">Kommentar zur Oberfläche<textarea aria-label="UI-Feedback-Kommentar" value={comment} onChange={event => setComment(event.target.value)} placeholder="Was soll an dieser Oberfläche anders werden?" rows={3} disabled={busy}/></label>
    <p className="markup-target-note">UI-Feedback für die Entwicklung dieser Erweiterung. Kein Szenenauftrag an den Blender-Agenten. Originalpixel bleiben unverändert.</p>
    {receipt && <p className="markup-feedback-receipt" role="status">{receipt}</p>}
    {error && <p className="bridge-error" role="alert">{error}</p>}
  </Modal>;
  function safelyPreview() { void showPreview(); }
}
