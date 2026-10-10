import {
  Check,
  ChevronRight,
  CircleAlert,
  CircleStop,
  Loader2,
  Wrench,
} from 'lucide-react';
import type { Preview, ToolPart } from '@/lib/agentStream';

const LABELS: Record<string, string> = {
  get_page_context: 'Lecture de la page',
  read_file: 'Lecture de la mémoire',
  append_journal: 'Note dans le journal',
  remember_fact: 'Mémorisation d’un fait',
  search_toolkits: 'Recherche de capacités',
  load_toolkit: 'Chargement des outils',
  get_workload: 'Analyse de la charge',
  get_fitness: 'Analyse de la forme',
  get_training_advice: 'Recommandations',
  get_personal_records: 'Records personnels',
  list_recent_sessions: 'Séances récentes',
  read_workout: 'Lecture de la séance',
  save_workout: 'Enregistrement de la séance',
  get_strength_progress: 'Progression en force',
  list_planned: 'Planning',
  inspect_planned_session: 'Lecture des étapes',
  update_session_prescription: 'Modification des étapes',
  list_garmin_devices: 'Appareils Garmin',
  export_garmin_sessions: 'Programmation dans Garmin',
  reconcile_garmin_session: 'Vérification Garmin',
  create_planned_session: 'Création d’une séance',
  update_planned_status: 'Mise à jour d’une séance',
  update_planned_session: 'Modification d’une séance',
  delete_planned_session: 'Suppression d’une séance',
};

function ToolPreview({ label, preview }: { label: string; preview?: Preview }) {
  if (!preview?.text) return null;
  let text = preview.text;
  if (!preview.truncated) {
    try {
      text = JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      /* Valid plain-text output. */
    }
  }
  return (
    <div className="mt-3 min-w-0">
      <p className="mb-1 text-[10px] uppercase tracking-wider text-text-muted">
        {label}
      </p>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-void/70 p-2.5 font-mono text-[11px] leading-relaxed text-text-secondary">
        {text}
      </pre>
      {preview.truncated && (
        <p className="mt-1 text-[10px] text-text-muted">
          Aperçu limité à 2 000 caractères.
        </p>
      )}
    </div>
  );
}

export function ToolActivity({ tools }: { tools: ToolPart[] }) {
  const running = tools.some((t) => t.status === 'running');
  const failed = tools.some((t) => t.status === 'error');
  return (
    <section
      aria-label="Activité des outils"
      className="my-3 overflow-hidden rounded-xl border border-text-muted/15 bg-shadow/35"
    >
      <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-text-muted">
        <Wrench className="size-3" />
        <span className="font-medium">
          {running ? 'En cours' : failed ? 'Activité · erreur' : 'Activité'}
        </span>
        <span className="ml-auto tabular-nums">
          {tools.length} {tools.length > 1 ? 'outils' : 'outil'}
        </span>
      </div>
      {tools.map((tool) => (
        <details key={tool.id} className="group border-t border-text-muted/10">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-xs hover:bg-text-muted/5 [&::-webkit-details-marker]:hidden">
            {tool.status === 'running' ? (
              <Loader2 className="size-3.5 shrink-0 animate-spin text-neon-cyan" />
            ) : tool.status === 'error' ? (
              <CircleAlert className="size-3.5 shrink-0 text-danger-red" />
            ) : tool.status === 'interrupted' ? (
              <CircleStop className="size-3.5 shrink-0 text-text-muted" />
            ) : (
              <Check className="size-3.5 shrink-0 text-success-green/80" />
            )}
            <span className="min-w-0 flex-1 text-text-secondary">
              {LABELS[tool.name] ?? tool.name}
            </span>
            <span className="text-[10px] text-text-muted">
              {tool.status === 'error'
                ? 'Échec'
                : tool.status === 'interrupted'
                  ? 'Interrompu'
                  : tool.status === 'running'
                    ? 'En cours'
                    : 'Terminé'}
            </span>
            {tool.elapsed_ms !== undefined && (
              <span className="text-[10px] tabular-nums text-text-muted">
                {(tool.elapsed_ms / 1000).toFixed(1)} s
              </span>
            )}
            <ChevronRight className="size-3 shrink-0 text-text-muted transition-transform group-open:rotate-90" />
          </summary>
          <div className="px-3 pb-3">
            <code className="text-[10px] text-text-muted">{tool.name}</code>
            <ToolPreview label="Paramètres" preview={tool.args} />
            <ToolPreview
              label={tool.status === 'error' ? 'Erreur' : 'Résultat'}
              preview={tool.output}
            />
          </div>
        </details>
      ))}
    </section>
  );
}
