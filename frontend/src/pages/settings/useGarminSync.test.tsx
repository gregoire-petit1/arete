// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { streamGarminSync } from '@/lib/garminSync';
import type { SyncResult } from '@/types';
import { useGarminSync } from './useGarminSync';

vi.mock('@/lib/garminSync', () => ({ streamGarminSync: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

function mount() {
  // Even a global retry policy must not replay a sync that may have written data.
  const client = new QueryClient({ defaultOptions: { mutations: { retry: 3 } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const hook = renderHook(useGarminSync, {
    wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  });
  return { ...hook, invalidate };
}

it('keeps progress visible, refreshes committed data after a failure, and never retries', async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(streamGarminSync).mockImplementationOnce((_options, onProgress) => {
    onProgress({ stage: 'fit', completed: 2, total: 5, activity_name: 'Course' });
    return new Promise<SyncResult>((_resolve, rejectRun) => { reject = rejectRun; });
  });
  const { result, invalidate } = mount();
  act(() => result.current.mutate({ max_activities: 50 }));
  await waitFor(() => expect(result.current.progress?.completed).toBe(2));
  act(() => reject(new Error('Connexion interrompue')));
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['syncStatus'] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['actual'] });
  expect(result.current.progress?.completed).toBe(2);
  expect(streamGarminSync).toHaveBeenCalledTimes(1);
});

it('aborts the stream when leaving the tab', async () => {
  let signal!: AbortSignal;
  vi.mocked(streamGarminSync).mockImplementationOnce((_options, _onProgress, runSignal) => {
    signal = runSignal;
    return new Promise<SyncResult>((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new Error('Suivi interrompu')), { once: true });
    });
  });
  const { result, unmount } = mount();
  act(() => result.current.mutate({ download_fit: true }));
  await waitFor(() => expect(result.current.isPending).toBe(true));
  unmount();
  expect(signal.aborted).toBe(true);
});
