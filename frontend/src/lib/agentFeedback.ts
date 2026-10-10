import { fetchAPI } from './api';

export interface TraceReceipt { trace_id: string; feedback_token: string }
export interface FeedbackState { user_score: 0 | 1 | null; reaction: string | null }
export interface MessageFeedback extends FeedbackState { status: 'saved' | 'pending' | 'uncertain' }
export type FeedbackKey = keyof FeedbackState;
export const EMPTY_FEEDBACK: FeedbackState = { user_score: null, reaction: null };
const FEEDBACK_TIMEOUT_MS = 30_000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isTraceReceipt(value: unknown): value is TraceReceipt {
  if (!value || typeof value !== 'object') return false;
  const t = value as TraceReceipt;
  return typeof t.trace_id === 'string' && UUID.test(t.trace_id) && typeof t.feedback_token === 'string' && /^[0-9a-f]{64}$/.test(t.feedback_token);
}

export function isEmoji(value: string): boolean {
  if (!value || Array.from(value).length > 32) return false;
  return Array.from(new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(value)).length === 1 &&
    /\p{Extended_Pictographic}|\p{Regional_Indicator}{2}|[#*0-9]\uFE0F?\u20E3/u.test(value);
}

export function isFeedbackState(value: unknown): value is FeedbackState {
  if (!value || typeof value !== 'object') return false;
  const f = value as FeedbackState;
  return (f.user_score === null || f.user_score === 0 || f.user_score === 1) && (f.reaction === null || (typeof f.reaction === 'string' && isEmoji(f.reaction)));
}

export async function writeFeedback(trace: TraceReceipt, threadId: string, key: FeedbackKey, value: 0 | 1 | string | null): Promise<void> {
  await fetchAPI(`/agent/feedback/${trace.trace_id}`, {
    method: 'PUT', signal: AbortSignal.timeout(FEEDBACK_TIMEOUT_MS),
    body: JSON.stringify({ thread_id: threadId, feedback_token: trace.feedback_token, key, value }),
  });
}

export async function readFeedback(trace: TraceReceipt, threadId: string): Promise<FeedbackState> {
  const state: unknown = await fetchAPI(`/agent/feedback/${trace.trace_id}/read`, {
    method: 'POST', signal: AbortSignal.timeout(FEEDBACK_TIMEOUT_MS),
    body: JSON.stringify({ thread_id: threadId, feedback_token: trace.feedback_token }),
  });
  if (!isFeedbackState(state)) throw new Error('Retour enregistré invalide.');
  return state;
}
