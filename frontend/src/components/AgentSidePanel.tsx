import { useEffect, useRef, useState } from 'react';
import { Bot, BotMessageSquare, Send, Loader2, Wrench, X, Check, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePanelContext, type PanelPageContext } from '@/lib/pageContext';

type ToolStatus = 'running' | 'done';

interface ToolCallStep {
  kind: 'tool';
  name: string;
  args?: string;
  status: ToolStatus;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  /** Tool-call timeline that happened while producing this message. */
  steps?: ToolCallStep[];
}

interface ToolEvent {
  type: 'tool_start' | 'tool_end';
  name: string;
  args?: string;
}

type StreamEvent =
  | { type: 'token'; text: string }
  | ToolEvent
  | { type: 'done' }
  | { type: 'error'; detail: string };

const TOOL_LABELS: Record<string, (args?: string) => string> = {
  get_page_context: (args?: string) => `lit les données de la page ${args ?? '…'}`,
  read_file: () => 'lit sa mémoire',
  write_file: () => 'écrit dans son journal',
  edit_file: () => 'met à jour son journal',
  ls: () => 'liste sa mémoire',
  glob: () => 'cherche dans sa mémoire',
  grep: () => 'cherche dans sa mémoire',
  search_toolkits: (args) => `cherche un toolkit${args ? `: ${args}` : ''}`,
  load_toolkit: (args) => `charge le toolkit ${args ?? '…'}`,
  list_planned: () => 'liste les séances planifiées',
  create_planned_session: () => 'crée une séance planifiée',
  update_planned_status: () => 'met à jour une séance',
  delete_planned_session: () => 'supprime une séance',
};

function toolLabel(name: string, args?: string): string {
  const fn = TOOL_LABELS[name];
  return fn ? fn(args) : name;
}

/**
 * Consume the POST /api/agent/chat/stream SSE run, emitting callbacks for
 * tool events and token deltas. Returns the full final text.
 */
async function runAgentStream(
  history: ChatMessage[],
  panelContext: PanelPageContext,
  onTool: (event: ToolEvent) => void,
  onToken: (text: string) => void,
): Promise<string> {
  const response = await fetch('/api/agent/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: history.map(({ role, content }) => ({ role, content })),
      panel_context: panelContextToPayload(panelContext),
    }),
  });
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => '');
    throw new Error(`API Error ${response.status}: ${detail}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalText = '';

  // SSE frames are `data: <json>\n\n`; accumulate until the double newline.
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (!frame.startsWith('data: ')) continue;
      let event: StreamEvent;
      try {
        event = JSON.parse(frame.slice(6)) as StreamEvent;
      } catch {
        continue;
      }
      if (event.type === 'token') {
        finalText += event.text;
        onToken(event.text);
      } else if (event.type === 'tool_start' || event.type === 'tool_end') {
        onTool(event);
      } else if (event.type === 'error') {
        throw new Error(event.detail);
      }
    }
  }
  return finalText;
}

/**
 * Coaching-agent side panel (port of the Cortex sidepanel, single-page flavor):
 * right drawer, streamed answers over SSE, current page sent as
 * `panel_context` on every message. Tool calls render as a persistent
 * per-message timeline. History is client state only — persistence lands later.
 */
export function AgentSidePanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const panelContext = usePanelContext();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [seenPage, setSeenPage] = useState(panelContext.page);
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Reset history when the page changes: context switches, so an old
  // conversation would be grounded in stale data. Render-phase state
  // adjustment (React's "adjust state when a prop changes" pattern — same as
  // Modal.tsx) instead of a setState-in-effect, which the lint rules ban.
  if (panelContext.page !== seenPage) {
    setSeenPage(panelContext.page);
    setMessages([]);
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const busy = streaming;

  const send = () => {
    const content = input.trim();
    if (!content || busy) return;
    const history = [...messages, { role: 'user' as const, content }];
    setMessages([...history, { role: 'assistant', content: '', steps: [] }]);
    setInput('');
    setStreaming(true);

    const patchLast = (patch: (m: ChatMessage) => ChatMessage) => {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === 'assistant') next[next.length - 1] = patch(last);
        return next;
      });
    };

    runAgentStream(
      history,
      panelContext,
      (event) => {
        patchLast((m) => {
          const steps = m.steps ?? [];
          if (event.type === 'tool_start') {
            return { ...m, steps: [...steps, { kind: 'tool', name: event.name, args: event.args, status: 'running' }] };
          }
          // tool_end: mark the last running call with this name as done.
          let idx = -1;
          for (let k = steps.length - 1; k >= 0; k--) {
            const s = steps[k];
            if (s.kind === 'tool' && s.name === event.name && s.status === 'running') {
              idx = k;
              break;
            }
          }
          if (idx === -1) return m;
          const next = [...steps];
          next[idx] = { ...next[idx], status: 'done' as const };
          return { ...m, steps: next };
        });
      },
      (text) => {
        patchLast((m) => ({ ...m, content: m.content + text }));
      },
    )
      .then((finalText) => {
        patchLast((m) => ({ ...m, content: finalText }));
      })
      .catch((error: unknown) => {
        const detail = error instanceof Error ? error.message : 'Erreur inconnue';
        patchLast((m) => ({ ...m, content: `Erreur — ${detail}` }));
      })
      .finally(() => setStreaming(false));
  };

  if (!open) return null;
  const page = seenPage;

  return (
    <aside
      className={cn(
        'fixed right-0 top-0 z-40 h-full w-full max-w-md bg-abyss/95 backdrop-blur-md',
        'border-l border-text-muted/20 flex flex-col animate-fade-left'
      )}
      role="complementary"
      aria-label="Coach IA"
    >
      <header className="flex items-center gap-2 px-4 py-3 border-b border-text-muted/20">
        <Bot className="size-5 text-neon-cyan" />
        <h2 className="font-semibold">Coach</h2>
        <span className="text-xs text-text-muted">· page : {page}</span>
        <button
          onClick={() => setMessages([])}
          disabled={busy || messages.length === 0}
          className="ml-auto p-1.5 rounded hover:bg-text-muted/10 text-text-muted disabled:opacity-30"
          aria-label="Nouvelle conversation"
          title="Nouvelle conversation"
        >
          <Trash2 className="size-4" />
        </button>
        <button
          onClick={onClose}
          className="p-1.5 rounded hover:bg-text-muted/10 text-text-muted"
          aria-label="Fermer le panneau"
        >
          <X className="size-5" />
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center mt-8 space-y-3">
            <BotMessageSquare className="size-10 mx-auto text-text-muted/50" />
            <p className="text-sm text-text-muted">
              Demande ton coach — il voit la page {page} et peut lire tes données.
              <br />
              <span className="text-xs">Charge le toolkit « planning » pour qu'il planifie tes séances.</span>
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={cn(m.role === 'user' && 'flex flex-col items-end')}>
            {m.steps && m.steps.length > 0 && (
              <div className={cn('space-y-1 mb-1.5', m.role === 'user' && 'items-end')}>
                {m.steps.map((step, j) => (
                  <div
                    key={j}
                    className="flex items-center gap-1.5 text-[11px] text-text-muted"
                  >
                    {step.status === 'running' ? (
                      <Loader2 className="size-3 animate-spin text-neon-cyan" />
                    ) : (
                      <Check className="size-3 text-success-green" />
                    )}
                    <Wrench className="size-3" />
                    <span>{toolLabel(step.name, step.args)}</span>
                  </div>
                ))}
              </div>
            )}
            {(m.content || m.role === 'user') && (
              <div
                className={cn(
                  'max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap',
                  m.role === 'user' ? 'bg-neon-purple/20' : 'glass-panel'
                )}
              >
                {m.content}
              </div>
            )}
          </div>
        ))}
        {busy && messages[messages.length - 1]?.content === '' && (
          <div className="flex items-center gap-2 text-text-muted text-sm">
            <Loader2 className="size-4 animate-spin" /> le coach réfléchit…
          </div>
        )}
      </div>

      <footer className="p-3 border-t border-text-muted/20">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
            placeholder="Pose ta question…"
            className="flex-1 bg-abyss/50 border border-text-muted/20 rounded px-3 py-2 text-sm focus:outline-none focus:border-neon-cyan/50"
            disabled={busy}
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="p-2 rounded bg-neon-purple/20 hover:bg-neon-purple/30 disabled:opacity-40"
            aria-label="Envoyer"
          >
            <Send className="size-4" />
          </button>
        </div>
      </footer>
    </aside>
  );
}

function panelContextToPayload(ctx: PanelPageContext): Record<string, string> {
  const payload: Record<string, string> = { page: ctx.page, path: ctx.path };
  for (const [key, value] of Object.entries(ctx.params)) {
    payload[`param_${key}`] = value;
  }
  return payload;
}
