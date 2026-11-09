import React from 'react';
import {FileTypeIcon, IconCheckOutlineRegular, IconCloseOutlineRegular} from '@deepseek-ai/dsh-client-ui-primitives';
import type {WireTool} from './bridge';

// A view classification of an actual tool event, never inferred from a prompt,
// elapsed time or a render/3D job that happens to contain the word "generate".
export function isImageGeneration(tool: Pick<WireTool, 'tool_name' | 'kind'>) {
  const identity = tool.tool_name.split(/[./]/).at(-1)?.replaceAll('-', '_').toLowerCase();
  return ['imagegeneration', 'imagegenerationcall', 'image_generation_call'].includes(String(tool.kind).toLowerCase())
    || ['imagegen', 'imagegeneration', 'image_generation', 'image_generation_call', 'imagegenerationcall', 'generate_image', 'image_generate', 'text_to_image', 'image_gen__imagegen'].includes(identity || '')
    || /(?:^|__)image_gen__imagegen$/.test(tool.tool_name);
}
export function ImageGenerationStatus({tool, hasImage}: {tool: Pick<WireTool, 'status' | 'error'>; hasImage: boolean}) {
  const state = ['interrupted', 'cancelled', 'canceled'].includes(tool.status) ? 'cancelled'
    : tool.status === 'failed' || tool.error ? 'failed'
      : ['running', 'preparing', 'inProgress', 'in_progress'].includes(tool.status) ? 'running' : 'completed';
  const label = state === 'running' ? 'Bild wird erstellt' : state === 'failed' ? 'Bild konnte nicht erstellt werden'
    : state === 'cancelled' ? 'Bilderstellung abgebrochen' : hasImage ? 'Bild erstellt' : 'Bilderstellung beendet';
  return <div className="image-generation-status" data-generation-state={state} role={state === 'failed' ? 'alert' : 'status'} aria-live="polite">
    <div className="image-generation-symbol" aria-hidden="true">{state === 'completed' ? <IconCheckOutlineRegular size={22}/> : state === 'cancelled' ? <IconCloseOutlineRegular size={22}/> : state === 'failed' ? <span>!</span> : <FileTypeIcon path="image.png"/>}<span className="image-generation-sweep"/></div>
    <div><strong>{label}</strong>{state === 'running' ? <small>Ergebnis erscheint hier, sobald es verfügbar ist.</small> : state === 'completed' && !hasImage ? <small>Kein Bild im Chat verfügbar. Werkzeugdetails prüfen.</small> : null}</div>
    {state === 'running' && <span className="image-generation-pulse" aria-hidden="true"/>}
  </div>;
}
