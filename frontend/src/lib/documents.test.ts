import { afterEach, expect, it, vi } from 'vitest';
import { uploadDocument, MAX_FILE_BYTES, documentsApi } from './documents';
import { parseEvent, applyEvent } from './agentStream';
import { restoreConversation } from './agentConversation';

afterEach(() => vi.unstubAllGlobals());

it('uploads exact blocks, finalizes separately and never sends file bytes in chat', async () => {
  const calls: { path: string; body: unknown; method: string }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (path, init) => {
    calls.push({ path: String(path), body: init.body, method: init.method });
    return new Response(JSON.stringify({ id: 'doc', status: 'ready' }), { status: 200 });
  }));
  const file = new File(['# Course\n30 minutes'], 'plan.md');
  await uploadDocument('thread', file, new AbortController().signal, () => {});
  expect(calls.map(c => c.method)).toEqual(['POST', 'PUT', 'POST']);
  expect(calls[1].path).toContain('/chunks/0');
  expect(await (calls[1].body as Blob).text()).toBe(await file.text());
  expect(calls[2].body).toBe('null');
});

it('rejects oversized and unsupported files before network I/O', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  await expect(uploadDocument('t', new File(['hello'], 'program.exe'), new AbortController().signal, () => {})).rejects.toThrow('Format');
  const file = new File(['a'], 'plan.md');
  Object.defineProperty(file, 'size', { value: MAX_FILE_BYTES + 1 });
  await expect(uploadDocument('t', file, new AbortController().signal, () => {})).rejects.toThrow('20 Mio');
  expect(fetch).not.toHaveBeenCalled();
});

it('does not retry an upload or confirmation after a failed response', async () => {
  const fetch = vi.fn().mockRejectedValue(new Error('réseau perdu')); vi.stubGlobal('fetch', fetch);
  await expect(documentsApi.confirm('thread', { id: 'draft', version: 1, status: 'draft', sessions: [], session_ids: [] }, [0], 'key')).rejects.toThrow('réseau perdu');
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('preserves import preview references through SSE and browser restoration', () => {
  const event = parseEvent(JSON.stringify({ type: 'import_preview', id: '11111111-1111-4111-8111-111111111111', version: 2 }));
  if (!event) throw new Error('Expected import preview event');
  const message = applyEvent({ role: 'assistant', content: 'Aperçu prêt' }, event);
  expect(restoreConversation(JSON.stringify([message]))[0].imports).toEqual(message.imports);
  expect(() => parseEvent(JSON.stringify({ type: 'import_preview', id: 'fake', version: -1 }))).toThrow();
});

it('verifies original bytes before making them available to an inline preview', async () => {
  const { originalDocument } = await import('./documents');
  const bytes = new TextEncoder().encode('source image bytes');
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const sha256 = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
  const doc = { id: 'doc', name: 'scan.png', status: 'ready' as const, size: bytes.length, sha256 };
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response(bytes)));
  const original = await originalDocument('thread', doc);
  expect(original.type).toBe('image/png');
  expect(await original.text()).toBe('source image bytes');
  await expect(originalDocument('thread', { ...doc, sha256: '0'.repeat(64) })).rejects.toThrow('Empreinte');
});
