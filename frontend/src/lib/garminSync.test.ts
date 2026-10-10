import { describe, expect, it, vi } from 'vitest';
import { consumeGarminSync, streamGarminSync } from './garminSync';
import { authFetch } from './auth';

vi.mock('./auth', () => ({ authFetch: vi.fn() }));
const result = { type: 'done', success: true, activities_synced: 1, activities_merged: 0, activities_matched: 0, activities_skipped: 0, errors: [], last_activity_date: null };
const progress = { type: 'progress', stage: 'fit', completed: 1, total: 3, activity_name: 'Séance à pied' };
const frame = (event: unknown) => `data: ${JSON.stringify(event)}\r\n\r\n`;
function body(text: string, split = false) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({ start(controller) {
    if (split) for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
    else controller.enqueue(bytes);
    controller.close();
  } });
}

describe('Garmin progress transport', () => {
  it('handles split UTF-8, CRLF and several events in one chunk', async () => {
    for (const split of [false, true]) {
      const received = vi.fn();
      expect(await consumeGarminSync(body(frame(progress) + frame(result), split), received)).toEqual(result);
      expect(received).toHaveBeenCalledExactlyOnceWith(progress);
    }
  });
  it('requires a terminal result even after all activities are processed', async () => {
    await expect(consumeGarminSync(body(frame({ ...progress, completed: 3 })), vi.fn())).rejects.toThrow('Suivi interrompu');
  });
  it('reports server errors and rejects invalid counters', async () => {
    await expect(consumeGarminSync(body(frame({ type: 'error', detail: 'Garmin indisponible' })), vi.fn())).rejects.toThrow('Garmin indisponible');
    await expect(consumeGarminSync(body(frame({ ...progress, completed: 4 })), vi.fn())).rejects.toThrow('invalide');
  });
  it('preserves partial results instead of inventing a complete success', async () => {
    const partial = { ...result, errors: ['FIT indisponible'] };
    expect(await consumeGarminSync(body(frame(partial)), vi.fn())).toEqual(partial);
  });
  it('sends one authenticated POST and never retries HTTP failures', async () => {
    vi.mocked(authFetch).mockResolvedValueOnce(new Response('{"detail":"Connecte Garmin"}', { status: 409 }));
    await expect(streamGarminSync({ max_activities: 50 }, vi.fn(), new AbortController().signal)).rejects.toThrow('Connecte Garmin');
    expect(authFetch).toHaveBeenCalledTimes(1);
    expect(authFetch).toHaveBeenCalledWith('/api/garmin/sync/activities/stream', expect.objectContaining({ method: 'POST', body: '{"max_activities":50}' }));
  });
});
