import type { ChatMessage, ToolPart } from './agentStream';

/** Presentation only: permissions and execution remain server-owned. */
const TOOL_LABELS: Record<string, [running: string, done: string]> = {
  read_file: ['Lecture de tes notes', 'Notes consultées'],
  ls: ['Recherche dans tes notes', 'Recherche terminée'],
  glob: ['Recherche dans tes notes', 'Recherche terminée'],
  grep: ['Recherche dans tes notes', 'Recherche terminée'],
  edit_file: ['Mise à jour de tes notes', 'Notes mises à jour'],
  delete: ['Suppression dans tes notes', 'Suppression terminée'],
  append_journal: ['Mise à jour du journal', 'Journal à jour'],
  remember_fact: ['Mise à jour de ton profil', 'Information enregistrée'],
  search_toolkits: ['Recherche de capacités', 'Capacités trouvées'],
  load_toolkit: ['Préparation des outils', 'Outils prêts'],
  get_workload: ['Analyse de la charge', 'Charge analysée'],
  get_fitness: ['Analyse de la forme', 'Forme analysée'],
  get_training_advice: ['Préparation des recommandations', 'Analyse terminée'],
  get_personal_records: ['Lecture de tes records', 'Records consultés'],
  list_recent_sessions: ['Lecture de tes séances', 'Séances consultées'],
  read_workout: ['Lecture de la séance', 'Séance consultée'],
  save_workout: ['Enregistrement de la séance', 'Séance enregistrée'],
  get_strength_progress: ['Lecture de ta progression en force', 'Progression en force consultée'],
  list_planned: ['Lecture du planning', 'Planning consulté'],
  inspect_planned_session: ['Lecture des étapes', 'Étapes consultées'],
  update_session_prescription: ['Modification des étapes', 'Étapes mises à jour'],
  list_garmin_devices: ['Recherche des appareils Garmin', 'Appareils consultés'],
  export_garmin_sessions: ['Programmation dans Garmin', 'Action Garmin terminée'],
  reconcile_garmin_session: ['Vérification Garmin', 'Vérification terminée'],
  create_planned_session: ['Création d’une séance', 'Séance créée'],
  update_planned_status: ['Mise à jour d’une séance', 'Séance mise à jour'],
  update_planned_session: ['Modification d’une séance', 'Séance mise à jour'],
  delete_planned_session: ['Suppression d’une séance', 'Séance supprimée'],
};

export function toolLabel(tool: Pick<ToolPart, 'name' | 'status'>): string {
  return TOOL_LABELS[tool.name]?.[tool.status === 'done' ? 1 : 0]
    ?? (tool.status === 'done' ? 'Action terminée' : 'Action en cours');
}

export function messageTools(message: ChatMessage): ToolPart[] {
  return message.parts?.filter((part): part is ToolPart => part.kind === 'tool') ?? [];
}

/** Replaying the whole prompt can repeat an already-committed write, including
 * one whose reply was lost. Follow-up messages retain the original evidence. */
export function canRetryMessage(message: ChatMessage): boolean {
  return !message.workouts?.length
    && !message.imports?.length
    && !message.parts?.some(part => part.kind === 'tool' || part.kind === 'calendar_action');
}
