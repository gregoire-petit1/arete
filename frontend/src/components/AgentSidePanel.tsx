import { WorkoutSelection } from './WorkoutSelection';
import { memo, useEffect, useRef, useState } from 'react';
import {
  ArrowDown,
  Bot,
  BotMessageSquare,
  CircleAlert,
  Send,
  Loader2,
  X,
  Plus,
  History,
  ChevronDown,
  RotateCcw,
  Square,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePanelContext } from '@/lib/pageContext';
import {
  MAX_MESSAGE_CHARS,
  type ChatMessage,
  type ChatPart,
  type ToolPart,
} from '@/lib/agentStream';
import { useCoachThreads } from '@/hooks/useCoachThreads';
import { followUps, starters } from '@/lib/coachPrompts';
import { ThreadHistory } from './agent/ThreadHistory';
import { AgentMarkdown } from './agent/AgentMarkdown';
import { ToolActivity } from './agent/ToolActivity';
import { DocumentAttachments, type AttachmentsHandle } from './agent/DocumentAttachments';
import { DocumentImports } from './agent/DocumentImports';

const PAGE_LABELS: Record<string, string> = {
  dashboard: 'Tableau de bord',
  planning: 'Planning',
  analytics: 'Analyses',
  log: 'Carnet',
  settings: 'Paramètres',
};
/** On a phone, Enter inserts a new line: the keyboard has no Shift to hold. */
const touchKeyboard = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(pointer: coarse)').matches === true;

/** Seconds since the answer started: a free model can take 30 s, say so. */
function useElapsedSeconds(running: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) return;
    const started = Date.now();
    const timer = setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      1000
    );
    return () => {
      clearInterval(timer);
      setSeconds(0);
    };
  }, [running]);
  return seconds;
}

/** One activity card per answer, where its first tool ran; texts in order.
 *  A card per tool round read as several answers stacked on each other. */
const MessageSurfaces = memo(function MessageSurfaces({
  message,
  onAction,
  locked,
}: {
  onAction?: (text: string) => void;
  locked?: boolean;
  message: ChatMessage;
}) {
  const parts: ChatPart[] = message.parts?.length
    ? message.parts
    : message.content
      ? [{ kind: 'text', id: 'answer', text: message.content }]
      : [];
  const tools = parts.filter((part): part is ToolPart => part.kind === 'tool');
  const groups: (ChatPart | ToolPart[])[] = [];
  for (const part of parts) {
    if (part.kind === 'text') {
      if (part.text.trim()) groups.push(part);
    } else if (part === tools[0]) groups.push(tools);
  }
  return (
    <>
      {groups.map((part) =>
        Array.isArray(part) ? (
          <ToolActivity key={`tool-${part[0].id}`} tools={part} />
        ) : part.kind === 'text' ? (
          <AgentMarkdown key={`text-${part.id}`} text={part.text} />
        ) : null
      )}
      {!!message.workouts?.length && <WorkoutSelection sessions={message.workouts} onResult={onAction} locked={locked} />}
      {message.error && (
        <div
          role="alert"
          className="mt-3 flex gap-2 rounded-lg border border-danger-red/20 bg-danger-red/5 p-3 text-xs leading-relaxed text-danger-red"
        >
          <CircleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{message.error}</span>
        </div>
      )}
      {message.interrupted && (
        <p className="mt-3 text-xs text-text-muted">Réponse interrompue. Les séances déjà enregistrées sont conservées ; vérifie Garmin avant tout nouvel envoi.</p>
      )}
    </>
  );
});

export function AgentSidePanel({
  open,
  onClose,
  onBusyChange,
}: {
  open: boolean;
  onClose: () => void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const panelContext = usePanelContext();
  const coach = useCoachThreads(panelContext);
  const { active, store, runningId } = coach;
  const messages = active.messages;
  const attachmentsRef = useRef<AttachmentsHandle>(null);
  const [documentsBusy, setDocumentsBusy] = useState(false);
  const streaming = runningId === active.id;
  const busy = runningId !== null || documentsBusy;
  const elapsed = useElapsedSeconds(streaming);
  const asked = messages.filter((m) => m.role === 'user').map((m) => m.content);
  const [showHistory, setShowHistory] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [following, setFollowing] = useState(true);
  const followRef = useRef(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (followRef.current)
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, open, showHistory]);
  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);
  useEffect(() => {
    if (open && !showHistory) inputRef.current?.focus();
  }, [open, showHistory, active.id]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (deleteId) setDeleteId(null);
        else if (showHistory) setShowHistory(false);
        else onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose, showHistory, deleteId]);

  const followLatest = () => {
    followRef.current = true;
    setFollowing(true);
  };
  const selectThread = (id: string) => {
    coach.select(id);
    setShowHistory(false);
    followLatest();
  };
  const newThread = () => {
    coach.create();
    setShowHistory(false);
    followLatest();
  };
  const send = (prompt?: string) => {
    if (!busy && coach.send(prompt)) followLatest();
  };

  if (!open) return null;
  const page = PAGE_LABELS[panelContext.page] ?? panelContext.page;
  return (
    <aside
      onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }}
      onDrop={event => { event.preventDefault(); if (!busy) attachmentsRef.current?.upload(Array.from(event.dataTransfer.files)); }}
      id="coach-panel"
      className="coach-panel fixed right-0 z-40 flex w-full max-w-[520px] flex-col border-l border-text-muted/20 bg-abyss shadow-2xl animate-fade-in"
      role="complementary"
      aria-label="Coach IA"
    >
      <header className="flex shrink-0 items-center gap-3 border-b border-text-muted/15 px-5 py-4">
        <div className="flex size-9 items-center justify-center rounded-xl border border-neon-cyan/15 bg-neon-cyan/5">
          <Bot className="size-5 text-neon-cyan" />
        </div>
        <div>
          <h2 className="text-sm font-semibold">Coach Arete</h2>
          <p className="mt-0.5 text-[11px] text-text-muted">{page}</p>
        </div>
        <button
          onClick={() => setShowHistory((v) => !v)}
          className="ml-auto rounded-lg p-2 text-text-muted hover:bg-text-muted/10"
          aria-label="Historique des conversations"
          aria-expanded={showHistory}
          title="Historique des conversations"
        >
          <History className="size-4" />
        </button>
        <button
          onClick={newThread}
          className="rounded-lg p-2 text-text-muted hover:bg-text-muted/10"
          aria-label="Nouvelle conversation"
          title="Nouvelle conversation"
        >
          <Plus className="size-4" />
        </button>
        <button
          onClick={onClose}
          className="rounded-lg p-2 text-text-muted hover:bg-text-muted/10"
          aria-label="Masquer le coach"
          title="Masquer le coach"
        >
          <X className="size-5" />
        </button>
      </header>
      {coach.storageError && (
        <p
          role="alert"
          className="border-b border-warning-orange/20 bg-warning-orange/5 px-4 py-2 text-xs text-warning-orange"
        >
          {coach.storageError}
        </p>
      )}
      {coach.error && (
        <p role="alert" className="px-4 py-2 text-xs text-danger-red">
          {coach.error}
        </p>
      )}
      {deleteId && (
        <div
          role="alert"
          className="border-b border-text-muted/15 bg-shadow px-4 py-3 text-xs"
        >
          <p>
            Supprimer « {store.threads.find((t) => t.id === deleteId)?.title} »
            ? Cette conversation sera effacée de ce navigateur.
          </p>
          <div className="mt-2 flex gap-3">
            <button
              onClick={() => {
                coach.remove(deleteId);
                setDeleteId(null);
              }}
              className="rounded bg-danger-red/15 px-3 py-1.5 text-danger-red"
            >
              Supprimer
            </button>
            <button
              onClick={() => setDeleteId(null)}
              className="rounded px-3 py-1.5 text-text-muted"
            >
              Annuler
            </button>
          </div>
        </div>
      )}
      {showHistory ? (
        <ThreadHistory
          threads={store.threads}
          activeId={active.id}
          runningId={runningId}
          onSelect={selectThread}
          onCreate={newThread}
          onDelete={setDeleteId}
          onClose={() => setShowHistory(false)}
        />
      ) : (
        <>
          <button
            onClick={() => setShowHistory(true)}
            className="flex shrink-0 items-center gap-2 border-b border-text-muted/10 px-5 py-2.5 text-left text-xs text-text-secondary hover:bg-shadow/40"
            aria-label="Changer de conversation"
          >
            <span className="min-w-0 flex-1 truncate">{active.title}</span>
            <ChevronDown className="size-3.5 text-text-muted" />
          </button>
          {busy && !streaming && (
            <div
              role="status"
              className="border-b border-neon-cyan/10 bg-neon-cyan/5 px-4 py-3 text-xs text-text-secondary"
            >
              <p className="flex items-center gap-2">
                <Loader2 className="size-3 animate-spin" />
                Le coach répond dans un autre fil.
              </p>
              <button
                onClick={() => selectThread(runningId!)}
                className="mt-2 text-neon-cyan underline underline-offset-2"
              >
                Revenir à la réponse
              </button>
              <span className="mx-2">·</span>
              <button
                onClick={coach.stop}
                className="text-text-muted underline underline-offset-2"
              >
                Arrêter
              </button>
            </div>
          )}
          <div
            ref={scrollRef}
            onScroll={() => {
              const el = scrollRef.current;
              if (!el) return;
              const nearBottom =
                el.scrollHeight - el.scrollTop - el.clientHeight < 64;
              followRef.current = nearBottom;
              setFollowing(nearBottom);
            }}
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-6"
          >
            <DocumentAttachments key={active.id} threadId={active.id} compact={active.messages.length > 0} disabled={runningId !== null} ref={attachmentsRef} onBusy={setDocumentsBusy} onDocuments={coach.attachments} />
            <div className="my-3"><DocumentImports key={`imports-${active.id}`} threadId={active.id} /></div>
            {!messages.length && (
              <div className="mx-auto mt-10 max-w-sm">
                <BotMessageSquare className="mb-5 size-8 text-neon-cyan/70" />
                <h3 className="text-lg font-semibold">On prépare la suite ?</h3>
                <p className="mt-2 text-sm leading-relaxed text-text-muted">
                  Ta forme, tes séances, tes objectifs. Pose une question, je
                  consulte les données utiles.
                </p>
                <div className="mt-6 space-y-2">
                  {starters(panelContext.page).map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => send(prompt)}
                      disabled={busy}
                      className="block w-full rounded-xl border border-text-muted/15 px-3.5 py-3 text-left text-sm text-text-secondary hover:border-neon-cyan/30 hover:bg-neon-cyan/5"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="space-y-6">
              {messages.map((message, i) => (
                <article
                  key={`${active.id}-${i}`}
                  aria-label={
                    message.role === 'user' ? 'Ton message' : 'Réponse du coach'
                  }
                  className={cn(
                    'min-w-0',
                    message.role === 'user' && 'flex justify-end'
                  )}
                >
                  {message.role === 'user' ? (
                    <div className="max-w-[90%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-neon-purple/15 px-4 py-3 text-sm leading-relaxed">
                      {message.content}
                    </div>
                  ) : (
                    <div className="min-w-0">
                      <div className="mb-3 flex items-center gap-2 text-[11px] font-medium text-text-muted">
                        <Bot className="size-3.5 text-neon-cyan/70" /> ARETE
                      </div>
                      <MessageSurfaces message={message} locked={busy} onAction={text => coach.recordAction(active.id, text)} />
                      {i === messages.length - 1 && !busy && !message.pending && !message.workouts?.length && (
                        <button
                          onClick={() => coach.retry() && followLatest()}
                          className="mt-3 inline-flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary"
                        >
                          <RotateCcw className="size-3" />
                          {message.error || message.interrupted ? 'Réessayer' : 'Regénérer'}
                        </button>
                      )}
                      {i === messages.length - 1 && !busy && !message.pending &&
                        !message.error && !message.interrupted && (
                        <div aria-label="Suggestions de suivi" className="mt-4 flex flex-wrap gap-2">
                          {followUps(panelContext.page, asked).map((prompt) => (
                            <button
                              key={prompt}
                              onClick={() => send(prompt)}
                              className="rounded-xl border border-neon-cyan/20 px-3 py-2 text-left text-xs text-text-secondary hover:bg-neon-cyan/5"
                            >
                              {prompt}
                            </button>
                          ))}
                        </div>
                      )}
                      {streaming && i === messages.length - 1 && (
                        <div
                          role="status"
                          className="mt-3 flex items-center gap-2 text-xs text-text-muted"
                        >
                          <Loader2 className="size-3 animate-spin" />
                          {message.parts?.some(
                            (p) => p.kind === 'tool' && p.status === 'running'
                          )
                            ? 'Action en cours…'
                            : message.content
                              ? 'Rédaction…'
                              : elapsed < 1 ? 'Demande envoyée' : 'Préparation de la réponse…'}
                          {elapsed >= 3 && ` ${elapsed} s`}
                        </div>
                      )}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </div>
          {!following && (
            <button
              onClick={() => {
                followRef.current = true;
                setFollowing(true);
                scrollRef.current?.scrollTo({
                  top: scrollRef.current.scrollHeight,
                  behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
                });
              }}
              className="absolute bottom-36 right-5 flex items-center gap-1.5 rounded-full border border-text-muted/20 bg-shadow px-3 py-2 text-xs shadow-lg"
            >
              <ArrowDown className="size-3" /> Derniers messages
            </button>
          )}
          <footer className="shrink-0 border-t border-text-muted/15 bg-abyss px-4 pb-4 pt-3">
            <div className="flex items-end gap-2 rounded-xl border border-text-muted/20 bg-void/40 p-2 focus-within:border-neon-cyan/40">
              <textarea
                ref={inputRef}
                aria-label="Message au coach"
                value={active.draft}
                onChange={(e) => coach.draft(e.target.value)}
                rows={2}
                maxLength={MAX_MESSAGE_CHARS}
                onKeyDown={(e) => {
                  if (
                    e.key === 'Enter' &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing &&
                    !touchKeyboard()
                  ) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="Pose ta question…"
                className="max-h-36 min-w-0 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-relaxed outline-none"
              />
              {streaming ? (
                <button
                  onClick={coach.stop}
                  className="rounded-lg bg-text-muted/15 p-2.5 hover:bg-text-muted/25"
                  aria-label="Arrêter la réponse"
                >
                  <Square className="size-4" />
                </button>
              ) : (
                <button
                  onClick={() => send()}
                  disabled={busy || !active.draft.trim()}
                  className="rounded-lg bg-neon-cyan/15 p-2.5 text-neon-cyan hover:bg-neon-cyan/25 disabled:opacity-30"
                  aria-label="Envoyer"
                >
                  <Send className="size-4" />
                </button>
              )}
            </div>
            <p className="mt-2 text-center text-[10px] text-text-muted">
              {touchKeyboard()
                ? 'Touche Envoyer pour envoyer'
                : 'Entrée pour envoyer · Maj + Entrée pour une nouvelle ligne'}
            </p>
          </footer>
        </>
      )}
    </aside>
  );
}
