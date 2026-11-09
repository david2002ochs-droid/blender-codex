import React, {useEffect, useRef, useState} from 'react';
import {Button, IconCloseOutlineRegular} from '@deepseek-ai/dsh-client-ui-primitives';
import {action, loadImage, safely, useSource, wire, type Resource} from './bridge';
import {paint, type Mark, type Point} from './markup-editor';

/** Preserve the original gallery's single-click/keyboard lightbox; a double
 * click is an explicit image-edit gesture and routes only a real resource ID. */
export function GeneratedImageInteraction({images, children}: {images: {url: string; resource: Resource}[]; children: React.ReactNode}) {
  const state = useSource(wire);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const replay = useRef(false);
  useEffect(() => () => clearTimeout(timer.current), []);
  function match(target: EventTarget | null) {
    if (!(target instanceof Element)) return;
    const button = target.closest('button[data-variant]');
    const img = button?.querySelector('img');
    const entry = img && images.find(entry => entry.url === img.src);
    return entry && button ? {button: button as HTMLButtonElement, resource: entry.resource} : undefined;
  }
  if (!state.capabilities?.can_annotate_images) return <>{children}</>;
  return <div className="generated-image-interaction" onClickCapture={event => {
    const entry = match(event.target);
    if (!entry || replay.current || event.detail === 0) return;
    event.preventDefault(); event.stopPropagation(); clearTimeout(timer.current);
    if (event.detail === 1) timer.current = setTimeout(() => { replay.current = true; entry.button.click(); replay.current = false; }, 400);
  }} onDoubleClickCapture={event => {
    const entry = match(event.target); if (!entry) return;
    event.preventDefault(); event.stopPropagation(); clearTimeout(timer.current);
    safely(action('image_markup/open', {resource_ids: [entry.resource.id]}));
  }}>{children}</div>;
}

type Pin = {number: number; x: number; y: number; text: string};
function paintPin(ctx: CanvasRenderingContext2D, pin: Pin, width: number, height: number) {
  const radius = Math.max(10, Math.min(width, height) / 45), x = pin.x * width, y = pin.y * height;
  ctx.save(); ctx.fillStyle = '#3352df'; ctx.strokeStyle = '#fff'; ctx.lineWidth = Math.max(2, radius / 5);
  ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#fff'; ctx.font = `bold ${radius * 1.2}px sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(String(pin.number), x, y); ctx.restore();
}
function ImagePane({resource, editorId, threadId, close}: {resource: Resource; editorId: string; threadId: string; close: () => void}) {
  const [url, setUrl] = useState<string>();
  const [size, setSize] = useState<{width: number; height: number}>();
  const [marks, setMarks] = useState<Mark[]>([]), [pins, setPins] = useState<Pin[]>([]);
  const [tool, setTool] = useState<Mark['tool'] | 'pin'>('pin');
  const [color, setColor] = useState('#3352df');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<number>();
  const image = useRef<HTMLImageElement>(null), canvas = useRef<HTMLCanvasElement>(null), active = useRef<Mark>();
  const pointer = useRef<number>(); const [draft, setDraft] = useState<Mark>();
  useEffect(() => { let live = true; loadImage({id: resource.id}).then(url => { if (live) setUrl(url); }, error => { if (live) setError(error.message); }); return () => { live = false; }; }, [resource.id]);
  useEffect(() => {
    const ctx = canvas.current?.getContext('2d'); if (!ctx || !size) return;
    ctx.clearRect(0, 0, size.width, size.height);
    for (const mark of marks) paint(ctx, mark);
    if (draft) paint(ctx, draft);
    for (const pin of pins) paintPin(ctx, pin, size.width, size.height);
  }, [size, marks, pins, draft]);
  function point(event: React.PointerEvent<HTMLCanvasElement>): Point {
    const rect = event.currentTarget.getBoundingClientRect();
    return {x: Math.max(0, Math.min(size!.width, (event.clientX - rect.left) / rect.width * size!.width)), y: Math.max(0, Math.min(size!.height, (event.clientY - rect.top) / rect.height * size!.height))};
  }
  function begin(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!size || busy || event.button !== 0) return;
    event.preventDefault(); const at = point(event);
    if (tool === 'pin') {
      if (pins.length >= 50) { setError('Höchstens 50 Kommentare pro Bild.'); return; }
      const number = pins.reduce((max, pin) => Math.max(max, pin.number), 0) + 1;
      setPins(previous => [...previous, {number, x: at.x / size.width, y: at.y / size.height, text: ''}]); setSelected(number); return;
    }
    pointer.current = event.pointerId; event.currentTarget.setPointerCapture(event.pointerId);
    active.current = {tool, color, points: [at], width: Math.max(2, Math.min(size.width, size.height) / 180)}; setDraft(active.current);
  }
  function move(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!active.current || pointer.current !== event.pointerId) return;
    const at = point(event); active.current = {...active.current, points: active.current.tool === 'pen' ? [...active.current.points, at] : [active.current.points[0], at]}; setDraft(active.current);
  }
  function end(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!active.current || pointer.current !== event.pointerId) return;
    const mark = active.current;
    setMarks(previous => [...previous, mark]); active.current = undefined; pointer.current = undefined; setDraft(undefined);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }
  async function adopt() {
    if (!size || !image.current || busy) return;
    if (pins.some(pin => !pin.text.trim())) { setError('Bitte jedem nummerierten Pin einen Kommentar geben.'); return; }
    if (!marks.length && !pins.length) { setError('Setze einen Pin oder zeichne eine Änderung ein.'); return; }
    try {
      setBusy(true); setError('');
      const output = document.createElement('canvas'); output.width = size.width; output.height = size.height;
      const ctx = output.getContext('2d'); if (!ctx) throw new Error('PNG-Ausgabe nicht verfügbar.');
      ctx.drawImage(image.current, 0, 0); for (const mark of marks) paint(ctx, mark); for (const pin of pins) paintPin(ctx, pin, size.width, size.height);
      const blob = await new Promise<Blob>((resolve, reject) => output.toBlob(blob => blob ? resolve(blob) : reject(new Error('PNG-Ausgabe fehlgeschlagen.')), 'image/png'));
      const limit = Number(wire.getSnapshot().capabilities?.max_attachment_bytes || 8388608); if (blob.size > limit) throw new Error('Die markierte PNG überschreitet die Dateigrößengrenze.');
      const png_base64 = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('PNG konnte nicht gelesen werden.')); reader.readAsDataURL(blob); });
      const current = wire.getSnapshot(); if (current.thread_id !== threadId || current.image_markup?.id !== editorId) throw new Error('Der Chat hat gewechselt. Diese Markierungen werden nicht übernommen.');
      await action('image_markup/commit', {id: editorId, source_resource_id: resource.id, png_base64, comments: pins.map(pin => ({number: pin.number, text: pin.text.trim()}))});
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="image-annotation-pane" data-image-resource-id={resource.id}>
    <header><span title={resource.name}>{resource.name}</span><span className="image-original-badge">Original unverändert</span><Button variant="ghost" aria-label={`Bildansicht schließen: ${resource.name}`} disabled={busy} onClick={close}><IconCloseOutlineRegular size={16}/></Button></header>
    <div className="image-annotation-tools" role="toolbar" aria-label={`Bildwerkzeuge: ${resource.name}`}>
      {(['pin', 'pen', 'arrow', 'rectangle'] as const).map((value, index) => <Button key={value} variant={tool === value ? 'primary' : 'ghost'} aria-pressed={tool === value} disabled={busy} onClick={() => setTool(value)}>{['Pin', 'Stift', 'Pfeil', 'Rechteck'][index]}</Button>)}
      <input aria-label="Zeichenfarbe" type="color" value={color} disabled={busy} onChange={event => setColor(event.target.value)}/>
      <Button variant="ghost" disabled={busy || !marks.length} onClick={() => setMarks(previous => previous.slice(0, -1))}>Rückgängig</Button>
    </div>
    <div className="image-annotation-scroll"><div className="image-annotation-stage" data-mark-count={marks.length} data-pin-count={pins.length}>
      {url && <img ref={image} src={url} alt={`Original: ${resource.name}`} draggable={false} onLoad={event => { const width = event.currentTarget.naturalWidth, height = event.currentTarget.naturalHeight; if (width * height > 24000000) { setError('Das Bild überschreitet 24 Megapixel.'); return; } setSize({width, height}); }} onError={() => setError('Bild kann nicht gelesen werden.')}/>}
      {size && <canvas ref={canvas} width={size.width} height={size.height} aria-label={`Zeichenfläche: ${resource.name}`} onPointerDown={begin} onPointerMove={move} onPointerUp={end} onPointerCancel={() => { active.current = undefined; pointer.current = undefined; setDraft(undefined); }}/>}
    </div></div>
    <div className="image-pin-comments">{pins.length ? pins.map(pin => <label key={pin.number} className={pin.number === selected ? 'selected' : ''}><span>{pin.number}</span><textarea aria-label={`Kommentar zu Pin ${pin.number}: ${resource.name}`} placeholder={`Änderung bei Pin ${pin.number}`} maxLength={4000} rows={2} value={pin.text} disabled={busy} onFocus={() => setSelected(pin.number)} onChange={event => setPins(previous => previous.map(item => item.number === pin.number ? {...item, text: event.target.value} : item))}/><Button variant="ghost" aria-label={`Pin ${pin.number} entfernen`} disabled={busy} onClick={() => setPins(previous => previous.filter(item => item.number !== pin.number))}>×</Button></label>) : <p>Pin auf das Bild setzen und die gewünschte Änderung beschreiben.</p>}</div>
    {error && <p role="alert" className="bridge-error">{error}</p>}
    <footer><small>Markierte Kopie + Kommentare in den aktuellen Chat-Entwurf. Versand erfolgt über „Senden“ im Chat.</small><Button variant="primary" disabled={!size || busy || (!marks.length && !pins.length)} onClick={() => safely(adopt())}>{busy ? 'Übernehmen…' : 'In Chat übernehmen'}</Button></footer>
  </section>;
}

export function ImageAnnotationSurface() {
  const state = useSource(wire); const editor = state.image_markup;
  const [hidden, setHidden] = useState<string[]>([]);
  useEffect(() => setHidden([]), [editor?.id]);
  if (!editor?.active || !editor.id || editor.thread_id !== state.thread_id) return <div className="image-annotation-empty" role="status">Keine aktive Bildannotation in diesem Chat.</div>;
  const resources = editor.resources.filter(resource => !hidden.includes(resource.id));
  return <div className="image-annotation-surface" key={editor.id}>
    <header className="image-annotation-heading"><div><strong>Bilder annotieren</strong><small>Originale sind dem aktuellen Entwurf zugeordnet.</small></div><Button variant="ghost" aria-label="Bildeditor schließen" onClick={() => safely(action('image_markup/close', {id: editor.id}))}><IconCloseOutlineRegular size={18}/></Button></header>
    <div className="image-annotation-views">{resources.map(resource => <ImagePane key={`${editor.id}:${resource.id}`} resource={resource} editorId={editor.id} threadId={editor.thread_id} close={() => { if (resources.length === 1) safely(action('image_markup/close', {id: editor.id})); else setHidden(previous => [...previous, resource.id]); }}/>)}</div>
  </div>;
}
