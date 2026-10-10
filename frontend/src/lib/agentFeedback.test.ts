import { expect, it, vi } from 'vitest';
import { isEmoji, readFeedback, writeFeedback } from './agentFeedback';
import { applyEvent, parseEvent } from './agentStream';
import { restoreConversation } from './agentConversation';

const trace = { trace_id: '12345678-1234-4123-8123-123456789012', feedback_token: 'a'.repeat(64) };

it.each(['🎯', '👩🏽‍💻', '👨‍👩‍👧‍👦', '🇫🇷', '1️⃣', '❤️'])('accepts a single emoji grapheme: %s', value => expect(isEmoji(value)).toBe(true));
it.each(['', 'hello', '1', '🔥🔥', '🇫', '🔥'.repeat(33)])('rejects non-emoji or multiple reactions: %s', value => expect(isEmoji(value)).toBe(false));

it('keeps the root receipt and confirmed feedback on reload, flags in-flight writes as uncertain', () => {
  const event = parseEvent(JSON.stringify({ type: 'done', message: { role: 'assistant', content: 'Réponse' }, trace }));
  if (!event) throw new Error('Missing done event');
  const message = applyEvent({ role: 'assistant', content: '', pending: true }, event);
  const feedback = { user_score: 0, reaction: '👩🏽‍💻', status: 'saved' };
  const [restored] = restoreConversation(JSON.stringify([{ ...message, feedback }]));
  expect(restored.trace).toEqual(trace);
  expect(restored.feedback).toEqual(feedback);
  expect(restoreConversation(JSON.stringify([{ ...message, feedback: { ...feedback, status: 'pending' } }]))[0].feedback?.status).toBe('uncertain');
  expect(restoreConversation(JSON.stringify([{ role: 'assistant', content: 'Ancienne réponse' }]))[0].trace).toBeUndefined();
});

it('invalid optional receipts never turn completed answers into failures', () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  try {
    const event = parseEvent(JSON.stringify({ type: 'done', message: { role: 'assistant', content: 'Réponse' }, trace: { ...trace, trace_id: 'bad' } }));
    expect(event).toEqual({ type: 'done', message: { role: 'assistant', content: 'Réponse' } });
    expect(warn).toHaveBeenCalledOnce();
  } finally { warn.mockRestore(); }
});

it('sends only the selected root, receipt and feedback and never retries a failed write', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('unavailable', { status: 502 }));
  vi.stubGlobal('fetch', fetch);
  try {
    await expect(writeFeedback(trace, 'thread', 'reaction', '🎯')).rejects.toThrow();
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe(`/api/agent/feedback/${trace.trace_id}`);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ thread_id: 'thread', feedback_token: trace.feedback_token, key: 'reaction', value: '🎯' });
    fetch.mockResolvedValueOnce(new Response(JSON.stringify({ user_score: 1, reaction: null })));
    await expect(readFeedback(trace, 'thread')).resolves.toEqual({ user_score: 1, reaction: null });
  } finally { vi.unstubAllGlobals(); }
});
