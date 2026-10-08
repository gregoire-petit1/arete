import { Check, Loader2, MessageSquare, Plus, Trash2, X } from 'lucide-react';
import type { CoachThread } from '@/lib/agentThreads';

const DATE_FORMAT = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'short',
});

export function ThreadHistory({
  threads,
  activeId,
  runningId,
  onSelect,
  onCreate,
  onDelete,
  onClose,
}: {
  threads: CoachThread[];
  activeId: string;
  runningId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <section
      className="min-h-0 flex-1 overflow-y-auto px-4 py-5"
      aria-label="Conversations du coach"
    >
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Tes conversations</h3>
          <p className="mt-1 text-xs text-text-muted">
            Conservées dans ce navigateur
          </p>
        </div>
        <button
          onClick={onClose}
          aria-label="Revenir à la conversation"
          className="rounded-lg p-2 text-text-muted hover:bg-shadow"
        >
          <X className="size-4" />
        </button>
      </div>
      <button
        onClick={onCreate}
        className="mb-5 flex w-full items-center gap-2 rounded-xl border border-neon-cyan/20 bg-neon-cyan/5 px-3 py-3 text-sm text-neon-cyan hover:bg-neon-cyan/10"
      >
        <Plus className="size-4" /> Nouvelle conversation
      </button>
      <ul className="space-y-2">
        {[...threads]
          .sort((a, b) => b.updatedAt - a.updatedAt)
          .map((thread) => (
            <li
              key={thread.id}
              className={`group rounded-xl border ${thread.id === activeId ? 'border-neon-cyan/25 bg-neon-cyan/5' : 'border-text-muted/10 bg-shadow/25'}`}
            >
              <div className="flex items-center gap-1 p-1">
                <button
                  onClick={() => onSelect(thread.id)}
                  aria-current={thread.id === activeId ? 'true' : undefined}
                  className="flex min-w-0 flex-1 items-start gap-3 rounded-lg px-2 py-3 text-left hover:bg-text-muted/5"
                >
                  {thread.id === runningId ? (
                    <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-neon-cyan" />
                  ) : (
                    <MessageSquare className="mt-0.5 size-4 shrink-0 text-text-muted" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span
                      className="block truncate text-sm"
                      title={thread.title}
                    >
                      {thread.title}
                    </span>
                    <span className="mt-1 block text-[11px] text-text-muted">
                      {thread.id === runningId
                        ? 'Réponse en cours'
                        : thread.draft
                          ? 'Brouillon'
                          : thread.messages.length
                            ? 'Dernier échange'
                            : 'Nouveau fil'}{' '}
                      · {DATE_FORMAT.format(thread.updatedAt)}
                    </span>
                  </span>
                  {thread.id === activeId && (
                    <Check className="mt-1 size-3 shrink-0 text-neon-cyan" />
                  )}
                </button>
                <button
                  onClick={() => onDelete(thread.id)}
                  aria-label={`Supprimer « ${thread.title} »`}
                  title="Supprimer la conversation"
                  className="mr-1 rounded-lg p-2 text-text-muted hover:bg-danger-red/10 hover:text-danger-red"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </li>
          ))}
      </ul>
    </section>
  );
}
