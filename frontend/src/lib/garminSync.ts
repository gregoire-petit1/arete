import { authFetch } from './auth';
import { ApiError } from './api';
import type { SyncResult } from '@/types';

export interface SyncOptions {
  start_date?: string;
  end_date?: string;
  download_fit?: boolean;
  max_activities?: number;
}

const STAGES = ['preparing', 'fetching', 'processing', 'fit', 'saving', 'finalizing'] as const;
export interface SyncProgress {
  stage: typeof STAGES[number];
  completed: number;
  total: number | null;
  activity_name: string | null;
}

type SyncEvent =
  | ({ type: 'progress' } & SyncProgress)
  | ({ type: 'done' } & SyncResult)
  | { type: 'error'; detail: string };

const MAX_ACTIVITIES = 200;
const MAX_EVENTS = MAX_ACTIVITIES * 3 + 10;
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_READS = MAX_BYTES;
const SYNC_TIMEOUT_MS = 20 * 60 * 1000;
const INTERRUPTED = 'Suivi interrompu. Des activités peuvent déjà avoir été importées. Vérifie le résultat avant de relancer.';

function parseEvent(data: string): SyncEvent {
  const event = JSON.parse(data) as Record<string, unknown> | null;
  const count = (value: unknown) => Number.isInteger(value) && Number(value) >= 0 && Number(value) <= MAX_ACTIVITIES;
  if (event?.type === 'error' && typeof event.detail === 'string') return event as SyncEvent;
  if (event?.type === 'progress'
    && STAGES.includes(event.stage as SyncProgress['stage'])
    && count(event.completed)
    && (event.total === null || (count(event.total) && Number(event.completed) <= Number(event.total)))
    && (event.activity_name === null || typeof event.activity_name === 'string')) return event as SyncEvent;
  if (event?.type === 'done'
    && typeof event.success === 'boolean'
    && ['activities_synced', 'activities_merged', 'activities_matched', 'activities_skipped'].every(key => count(event[key]))
    && Array.isArray(event.errors) && event.errors.every(error => typeof error === 'string')
    && (event.last_activity_date === null || typeof event.last_activity_date === 'string')) return event as SyncEvent;
  throw new Error('Progression Garmin invalide.');
}

/** The terminal result is mandatory: a closed connection is never a successful sync. */
export async function consumeGarminSync(
  body: ReadableStream<Uint8Array>,
  onProgress: (progress: SyncProgress) => void,
): Promise<SyncResult> {
  const reader = body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let buffer = '';
  let bytes = 0;
  let events = 0;
  try {
    for (let reads = 0; reads < MAX_READS; reads++) {
      const { done, value } = await reader.read();
      if (done) throw new Error(INTERRUPTED);
      bytes += value.byteLength;
      if (bytes > MAX_BYTES) throw new Error('Réponse Garmin trop volumineuse.');
      buffer += decoder.decode(value, { stream: true });
      for (let frames = 0; frames <= MAX_EVENTS; frames++) {
        const separator = /\r?\n\r?\n/.exec(buffer);
        if (!separator) break;
        const frame = buffer.slice(0, separator.index);
        buffer = buffer.slice(separator.index + separator[0].length);
        if (++events > MAX_EVENTS) throw new Error('Trop d’événements Garmin.');
        const data = frame.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
        if (!data) continue;
        const event = parseEvent(data);
        if (event.type === 'error') throw new Error(event.detail);
        if (event.type === 'done') return event;
        onProgress(event);
      }
    }
    throw new Error('Limite de lecture Garmin atteinte.');
  } finally {
    try { await reader.cancel(); } finally { reader.releaseLock(); }
  }
}

export async function streamGarminSync(
  options: SyncOptions,
  onProgress: (progress: SyncProgress) => void,
  signal: AbortSignal,
): Promise<SyncResult> {
  try {
    const response = await authFetch('/api/garmin/sync/activities/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
      signal: AbortSignal.any([signal, AbortSignal.timeout(SYNC_TIMEOUT_MS)]),
    });
    if (!response.ok) {
      const error = new ApiError(response.status, await response.text());
      throw new Error(error.detail || error.message);
    }
    if (!response.body) throw new Error(INTERRUPTED);
    return await consumeGarminSync(response.body, onProgress);
  } catch (error) {
    if (error instanceof Error && ['AbortError', 'TimeoutError', 'TypeError'].includes(error.name)) {
      throw new Error(INTERRUPTED, { cause: error });
    }
    throw error;
  }
}
