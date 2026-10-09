import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { documentsApi } from '@/lib/documents';
import { invalidateAfterSession } from '@/lib/queryKeys';
import type { PanelPageContext } from '@/lib/pageContext';
import {
  applyEvent,
  MAX_MESSAGE_CHARS,
  requestWindow,
  runAgentStream,
  settleMessage,
  type ChatMessage,
} from '@/lib/agentStream';
import {
  addThread,
  createThread,
  loadThreads,
  removeThread,
  saveThreads,
  titleFromMessage,
  updateThread,
} from '@/lib/agentThreads';

// One model run for the whole coach. Switching threads can never fan out requests.
const MAX_ACTIVE_RUNS = 1;
const SAVE_DELAY_MS = 250;
const SESSION_WRITE_TOOLS = new Set([
  'create_planned_session',
  'update_planned_status',
  'update_planned_session',
  'delete_planned_session',
  'save_workout',
]);

export function useCoachThreads(context: PanelPageContext) {
  const queryClient = useQueryClient();
  const [initial] = useState(loadThreads);
  const [store, setStore] = useState(initial.store);
  const [storageError, setStorageError] = useState(initial.error);
  const [error, setError] = useState('');
  const [runningId, setRunningId] = useState<string | null>(null);
  const runRef = useRef<{
    threadId: string;
    controller: AbortController;
  } | null>(null);
  const storeRef = useRef(store);
  const active = store.threads.find((t) => t.id === store.activeId);
  if (!active)
    throw new Error('Invariant violated: active coach thread missing.');

  // Debounce writes while streaming and flush on page exit. Keep corrupt source
  // storage untouched if loading failed, and make quota errors visible in the UI.
  useEffect(() => {
    storeRef.current = store;
    if (initial.error) return;
    const timeout = window.setTimeout(
      () => setStorageError(saveThreads(storeRef.current)),
      SAVE_DELAY_MS
    );
    return () => window.clearTimeout(timeout);
  }, [store, initial.error]);
  useEffect(() => {
    const persist = () => {
      if (!initial.error) saveThreads(storeRef.current);
    };
    window.addEventListener('pagehide', persist);
    return () => {
      window.removeEventListener('pagehide', persist);
      persist();
      runRef.current?.controller.abort();
    };
  }, [initial.error]);

  const select = (id: string) => {
    setStore((prev) =>
      prev.threads.some((t) => t.id === id) ? { ...prev, activeId: id } : prev
    );
    setError('');
  };
  const create = () => {
    try {
      const candidate = createThread();
      addThread(store, candidate); // Check the bound before queuing the update.
      setStore((prev) => addThread(prev, candidate));
      setError('');
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Impossible de créer une conversation.'
      );
    }
  };
  const remove = async (id: string) => {
    if (runRef.current?.threadId === id) runRef.current.controller.abort();
    try { await documentsApi.deleteThread(id); }
    catch (err) { setError(err instanceof Error ? err.message : 'Suppression des documents impossible.'); return; }
    setStore((prev) => removeThread(prev, id));
    setError('');
  };
  const attachments = useCallback((ids: string[]) => {
    setStore(prev => updateThread(prev, active.id, thread => JSON.stringify(thread.attachmentIds ?? []) === JSON.stringify(ids) ? thread : { ...thread, attachmentIds: ids }));
  }, [active.id]);
  const draft = (text: string) =>
    setStore((prev) =>
      updateThread(prev, prev.activeId, (t) => ({ ...t, draft: text }))
    );
  const stop = useCallback(() => runRef.current?.controller.abort(), []);

  /** ``keep`` = messages kept before the new question (a retry drops the
   *  failed or unwanted answer and asks the same question again). */
  const send = (prompt = active.draft, keep = active.messages.length) => {
    const content = prompt.trim();
    const activeRuns = runRef.current ? 1 : 0;
    if (!content || activeRuns >= MAX_ACTIVE_RUNS) return false;
    const retrying = keep < active.messages.length;
    const history = requestWindow([
      ...active.messages.slice(0, keep).filter(
        (m) => m.content.trim() && !m.error && !m.interrupted
      ),
      { role: 'user', content },
    ]);
    if (history.some((m) => m.content.length > MAX_MESSAGE_CHARS)) {
      setError(
        'Un message dépasse 16 000 caractères. Raccourcis-le ou crée une nouvelle conversation.'
      );
      return false;
    }
    const threadId = active.id;
    const answerIndex = keep + 1;
    const controller = new AbortController();
    runRef.current = { threadId, controller };
    setRunningId(threadId);
    setError('');
    setStore((prev) =>
      updateThread(prev, threadId, (t) => ({
        ...t,
        title: t.messages.length ? t.title : titleFromMessage(content),
        draft: retrying ? t.draft : '',
        updatedAt: Date.now(),
        messages: [
          ...t.messages.slice(0, keep),
          { role: 'user', content },
          { role: 'assistant', content: '', parts: [], pending: true },
        ],
      }))
    );
    // Capture the originating thread and answer, never the currently selected
    // thread. Late events after switching or deletion cannot leak into a new thread.
    const patchAnswer = (patch: (message: ChatMessage) => ChatMessage) =>
      setStore((prev) =>
        updateThread(prev, threadId, (t) => {
          const message = t.messages[answerIndex];
          if (!message || message.role !== 'assistant') return t;
          return {
            ...t,
            updatedAt: Date.now(),
            messages: t.messages.map((m, i) =>
              i === answerIndex ? patch(m) : m
            ),
          };
        })
      );
    void runAgentStream(
      history,
      context,
      (event) => {
        patchAnswer((m) => applyEvent(m, event));
        if (event.type === 'import_preview' || event.type === 'done') void queryClient.invalidateQueries({ queryKey: ['coach-imports', threadId] });
        // Refresh when the write completes, even if the final answer fails or
        // the athlete has switched threads while this run was in flight.
        if (
          event.type === 'tool_end' &&
          event.status === 'done' &&
          SESSION_WRITE_TOOLS.has(event.name)
        )
          invalidateAfterSession(queryClient);
      },
      controller.signal,
      threadId
    )
      .catch((err: unknown) =>
        patchAnswer((m) =>
          settleMessage(
            m,
            controller.signal.aborted
              ? undefined
              : err instanceof Error
                ? err.message
                : 'Erreur inconnue.',
            controller.signal.aborted
          )
        )
      )
      .finally(() => {
        runRef.current = null;
        setRunningId(null);
      });
    return true;
  };
  /** Ask the last question again, replacing its answer. */
  const retry = () => {
    const last = active.messages.map((m) => m.role).lastIndexOf('user');
    return last >= 0 && send(active.messages[last].content, last);
  };

  return {
    store,
    active,
    runningId,
    error,
    storageError,
    select,
    create,
    remove,
    draft,
    attachments,
    send,
    retry,
    stop,
  };
}
