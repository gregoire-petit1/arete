import { isWorkoutUpdate, type WorkoutUpdate } from './workouts';
import { readableError } from './utils';
import type { PanelPageContext } from './pageContext';

export type ToolStatus = 'running' | 'done' | 'error' | 'interrupted';
export interface Preview {
  text: string;
  truncated: boolean;
}
export interface ToolPart {
  kind: 'tool';
  id: string;
  name: string;
  args?: Preview;
  output?: Preview;
  status: ToolStatus;
  elapsed_ms?: number;
}
export interface TextPart {
  kind: 'text';
  id: string;
  text: string;
}
export type ChatPart = ToolPart | TextPart;
export interface ChatMessage {
  workouts?: WorkoutUpdate[];
  imports?: { id: string; version: number }[];
  role: 'user' | 'assistant';
  content: string;
  parts?: ChatPart[];
  error?: string;
  interrupted?: boolean;
  pending?: boolean;
}
export type StreamEvent =
  | WorkoutUpdate
  | { type: 'import_preview'; id: string; version: number }
  | { type: 'token'; id: string; text: string }
  | { type: 'message'; id: string; text: string }
  | { type: 'tool_start'; id: string; name: string; args: Preview }
  | {
      type: 'tool_end';
      id: string;
      name: string;
      status: 'done' | 'error';
      output: Preview;
      elapsed_ms: number;
    }
  | { type: 'done'; message: { role: 'assistant'; content: string } }
  | { type: 'error'; detail: string };

/** Messages sent per turn. The thread keeps everything locally; the coach's
 *  journal is its long-term memory, so older turns need not be re-sent (they
 *  used to trigger a summarization request on every turn of a long thread). */
export const REQUEST_WINDOW_MESSAGES = 30;
export const MAX_MESSAGE_CHARS = 16_000;

/** The tail of a thread sent to the coach, starting on a question: some
 *  models refuse a conversation that opens with an assistant message. */
export function requestWindow(history: ChatMessage[]): ChatMessage[] {
  const window = history.slice(-REQUEST_WINDOW_MESSAGES);
  const start = window.findIndex((m) => m.role === 'user');
  return start < 0 ? [] : window.slice(start);
}
const MAX_STREAM_BYTES = 2_000_000;
const MAX_STREAM_EVENTS = 12_000;
const MAX_STREAM_READS = 24_000;
const STREAM_TIMEOUT_MS = 310_000;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object';
}
function isPreview(value: unknown): value is Preview {
  return (
    record(value) &&
    typeof value.text === 'string' &&
    typeof value.truncated === 'boolean'
  );
}

/** Fail explicitly on malformed events; losing one can leave a tool running forever. */
export function parseEvent(data: string): StreamEvent {
  const e: unknown = JSON.parse(data);
  if (!record(e)) throw new Error('Événement du coach invalide.');
  if (isWorkoutUpdate(e)) return e;
  if (e.type === 'import_preview' && typeof e.id === 'string' && /^[0-9a-f-]{36}$/i.test(e.id) && Number.isInteger(e.version) && Number(e.version) > 0) return e as StreamEvent;
  const identified = typeof e.id === 'string' && e.id.length > 0;
  if (
    identified &&
    (e.type === 'token' || e.type === 'message') &&
    typeof e.text === 'string'
  )
    return e as StreamEvent;
  if (identified && typeof e.name === 'string') {
    if (e.type === 'tool_start' && isPreview(e.args)) return e as StreamEvent;
    if (
      e.type === 'tool_end' &&
      isPreview(e.output) &&
      (e.status === 'done' || e.status === 'error') &&
      typeof e.elapsed_ms === 'number'
    )
      return e as StreamEvent;
  }
  if (e.type === 'error' && typeof e.detail === 'string')
    return e as StreamEvent;
  if (
    e.type === 'done' &&
    record(e.message) &&
    e.message.role === 'assistant' &&
    typeof e.message.content === 'string'
  )
    return e as StreamEvent;
  throw new Error('Événement du coach invalide.');
}

export function settleMessage(
  message: ChatMessage,
  error?: string,
  interrupted = false
): ChatMessage {
  return {
    ...message,
    error,
    interrupted,
    pending: false,
    parts: message.parts?.map((p) =>
      p.kind === 'tool' && p.status === 'running'
        ? { ...p, status: 'interrupted' }
        : p
    ),
  };
}

/** Message IDs and tool-call IDs are separate; same-name parallel calls never collide. */
export function applyEvent(
  message: ChatMessage,
  event: StreamEvent
): ChatMessage {
  if (event.type === 'workout_update') {
    const current = message.workouts ?? [];
    const previous = current.find(w => w.session.id === event.session.id);
    if (previous && (previous.session.revision > event.session.revision || previous.sequence >= event.sequence)) return message;
    if (!previous && current.length >= 50) throw new Error('Maximum 50 séances par réponse.');
    return { ...message, workouts: previous ? current.map(w => w.session.id === event.session.id ? event : w) : [...current, event] };
  }
  if (event.type === 'import_preview') return { ...message, imports: [...(message.imports ?? []).filter(item => item.id !== event.id), { id: event.id, version: event.version }] };
  if (event.type === 'error') return settleMessage(message, event.detail);
  if (event.type === 'done')
    return settleMessage({ ...message, content: event.message.content });
  const parts = [...(message.parts ?? [])];
  if (event.type === 'token' || event.type === 'message') {
    const idx = parts.findIndex((p) => p.kind === 'text' && p.id === event.id);
    const previous = idx < 0 ? undefined : parts[idx];
    const text =
      event.type === 'message'
        ? event.text
        : (previous?.kind === 'text' ? previous.text : '') + event.text;
    const part: TextPart = { kind: 'text', id: event.id, text };
    if (idx < 0) parts.push(part);
    else parts[idx] = part;
    return { ...message, content: text, parts };
  }
  const idx = parts.findIndex((p) => p.kind === 'tool' && p.id === event.id);
  const previous = idx < 0 ? undefined : parts[idx];
  const part: ToolPart =
    event.type === 'tool_start'
      ? {
          kind: 'tool',
          id: event.id,
          name: event.name,
          args: event.args,
          status: 'running',
        }
      : {
          ...(previous?.kind === 'tool' ? previous : {}),
          kind: 'tool',
          id: event.id,
          name: event.name,
          output: event.output,
          elapsed_ms: event.elapsed_ms,
          status: event.status,
        };
  if (idx < 0) parts.push(part);
  else parts[idx] = part;
  return { ...message, parts };
}

/** Bounded SSE decoder, also used in tests with deliberately split network chunks. */
export async function consumeStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let buffer = '';
  let bytes = 0;
  let events = 0;
  try {
    for (let reads = 0; reads < MAX_STREAM_READS; reads++) {
      const { done, value } = await reader.read();
      if (done)
        throw new Error('Connexion interrompue avant la fin de la réponse.');
      bytes += value.byteLength;
      if (bytes > MAX_STREAM_BYTES)
        throw new Error('Réponse du coach trop volumineuse.');
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(
        /\r\n/g,
        '\n'
      );
      for (let frames = 0; frames < MAX_STREAM_EVENTS; frames++) {
        const sep = buffer.indexOf('\n\n');
        if (sep < 0) break;
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const data = frame
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n');
        if (!data) continue;
        if (++events > MAX_STREAM_EVENTS)
          throw new Error('Trop d’événements dans la réponse.');
        const event = parseEvent(data);
        if (event.type === 'error') throw new Error(event.detail);
        onEvent(event);
        if (event.type === 'done') return;
      }
    }
    throw new Error('Le stream dépasse la limite de lecture.');
  } finally {
    try {
      await reader.cancel();
    } finally {
      reader.releaseLock();
    }
  }
}

export async function runAgentStream(
  history: ChatMessage[],
  context: PanelPageContext,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
  threadId: string
): Promise<void> {
  const panel_context: Record<string, string> = { page: context.page };
  for (const [key, value] of Object.entries(context.params))
    panel_context[`param_${key}`] = value;
  const response = await fetch('/api/agent/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: history.map(({ role, content }) => ({ role, content })),
      thread_id: threadId,
      panel_context,
    }),
    signal: AbortSignal.any([signal, AbortSignal.timeout(STREAM_TIMEOUT_MS)]),
  });
  if (!response.ok)
    throw new Error(
      `Le coach n'a pas pu répondre (${response.status}) : ${readableError(
        new Error(await response.text())
      )}`
    );
  if (!response.body) throw new Error('Le serveur ne fournit pas de stream.');
  await consumeStream(response.body, onEvent);
}
