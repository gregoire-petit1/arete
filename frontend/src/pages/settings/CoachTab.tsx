import { useQuery } from '@tanstack/react-query';
import { BookOpen, Brain, RefreshCw, Sunrise } from 'lucide-react';
import { Panel, Button } from '@/components/ui';
import type { SettingsTabProps } from './types';

interface LedgerFile {
  name: string;
  content: string;
}

interface LedgerResponse {
  files: LedgerFile[];
}

const FILE_META: Record<string, { label: string; icon: typeof Brain; hint: string }> = {
  'sessions.md': {
    label: 'Journal des séances',
    icon: BookOpen,
    hint: "Une entrée par séance dont le coach discute — faits, ressentis, décisions.",
  },
  'notes.md': {
    label: 'Notes durables',
    icon: Brain,
    hint: 'Observations long terme : blessures, préférences, objectifs.',
  },
};

/**
 * Settings tab for the coach: whether it writes a daily briefing, and the
 * memory ledger it keeps (data/agent/memory/*.md), read-only, via
 * GET /api/agent/memory.
 */
export function CoachTab({ settings, updateSetting }: SettingsTabProps) {
  const { data, isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: ['agentMemory'],
    queryFn: async (): Promise<LedgerResponse> => {
      const response = await fetch('/api/agent/memory');
      if (!response.ok) throw new Error(`API Error ${response.status}`);
      return response.json();
    },
    staleTime: 10_000,
  });


  const briefingSwitch = (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Sunrise className="size-4 text-neon-gold" /> Briefing du matin
        </span>
      }
    >
      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          className="accent-neon-cyan mt-0.5"
          checked={settings.coach_briefing_enabled}
          onChange={(e) => updateSetting('coach_briefing_enabled', e.target.checked)}
        />
        <span className="text-sm text-text-secondary">
          Après la synchronisation du matin, le coach lit tes données et écrit deux ou trois
          phrases sur ton tableau de bord.
          <br />
          <span className="text-xs text-text-muted">
            Décoché, le Dashboard garde le conseil calculé par les règles.
          </span>
        </span>
      </label>
    </Panel>
  );

  return (
    <div className="space-y-4">
      {briefingSwitch}
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-muted">
          Le coach tient son journal en markdown dans <code>data/agent/memory/</code>. Lecture seule.
        </p>
        <Button variant="ghost" onClick={() => refetch()} disabled={isRefetching}>
          <RefreshCw className={`size-4 ${isRefetching ? 'animate-spin' : ''}`} /> Rafraîchir
        </Button>
      </div>

      {isLoading && <p className="text-sm text-text-muted">Chargement du journal…</p>}
      {isError && (
        <Panel title="Mémoire du coach">
          <p className="text-sm text-danger-red">Ledger indisponible (backend à jour ?).</p>
          <Button variant="ghost" onClick={() => refetch()} className="mt-2">
            <RefreshCw className="size-4" /> Réessayer
          </Button>
        </Panel>
      )}

      {(data?.files ?? []).map((file) => {
        const meta = FILE_META[file.name] ?? { label: file.name, icon: BookOpen, hint: '' };
        const Icon = meta.icon;
        return (
          <Panel
            key={file.name}
            title={
              <span className="flex items-center gap-2">
                <Icon className="size-4 text-neon-cyan" /> {meta.label}
                <code className="text-xs text-text-muted">{file.name}</code>
              </span>
            }
          >
            {meta.hint && <p className="text-xs text-text-muted mb-2">{meta.hint}</p>}
            {file.content.trim() ? (
              <pre className="text-xs whitespace-pre-wrap bg-abyss/50 rounded p-3 max-h-96 overflow-y-auto border border-text-muted/10">
                {file.content}
              </pre>
            ) : (
              <p className="text-sm text-text-muted italic">
                Vide — discute d'une séance avec le coach pour remplir le journal.
              </p>
            )}
          </Panel>
        );
      })}
    </div>
  );
}
