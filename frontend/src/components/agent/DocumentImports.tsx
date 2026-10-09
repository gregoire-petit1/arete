import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, CalendarCheck2, ClipboardList, ShieldCheck } from 'lucide-react';
import { documentsApi, documentRequest, type Prescription, type ImportDraft } from '@/lib/documents';
import { invalidateAfterSession } from '@/lib/queryKeys';
import { PrescriptionEditor } from '../PrescriptionEditor';
import { Modal, ModalHeader } from '../ui';

function DraftEditor({ threadId, draft, onClose }: { threadId: string; draft: ImportDraft; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState(draft);
  const [sessions, setSessions] = useState(() => draft.sessions.map(item => structuredClone(item.session)));
  const [selected, setSelected] = useState(() => draft.sessions.map((_, index) => index));
  const [reviewed, setReviewed] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key, setKey] = useState(() => crypto.randomUUID());
  const patch = (index: number, change: Partial<typeof sessions[number]>) => {
    setSessions(previous => previous.map((session, i) => i === index ? { ...session, ...change } : session));
    setDirty(true); setReviewed(false); setKey(crypto.randomUUID());
  };
  const save = async () => {
    setBusy(true); setError('');
    try {
      const next = await documentsApi.update(threadId, current, sessions);
      setCurrent(next); setSessions(next.sessions.map(item => item.session)); setDirty(false); setReviewed(false);
      await queryClient.invalidateQueries({ queryKey: ['coach-imports', threadId] });
    } catch (error) { setError(error instanceof Error ? error.message : 'Enregistrement impossible.'); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    setBusy(true); setError('');
    try {
      await documentsApi.confirm(threadId, current, selected, key);
      invalidateAfterSession(queryClient);
      await queryClient.invalidateQueries({ queryKey: ['coach-imports', threadId] });
      onClose();
    } catch (error) { setError(error instanceof Error ? error.message : 'Confirmation impossible.'); }
    finally { setBusy(false); }
  };
  return <Modal open onClose={() => { if (!busy) onClose(); }} className="max-w-3xl max-h-[90dvh] overflow-y-auto rounded-xl border-white/10 bg-abyss!" label="Vérifier les séances importées">
    <ModalHeader title="Vérifier les séances importées" icon={<ClipboardList size={19} className="text-neon-cyan" />} tone="text-text-primary" onClose={() => { if (!busy) onClose(); }} />
    <p className="mb-6 text-sm leading-relaxed text-text-muted">Compare les dates, chiffres et unités aux sources. Décoche les séances à exclure ; plusieurs séances le même jour restent possibles.</p>
    <fieldset disabled={busy} className="space-y-4">
      {sessions.map((session, index) => <section key={index} className="rounded-xl border border-white/10 bg-white/[0.015] p-4 space-y-4 sm:p-5">
        <label className="flex items-center gap-2.5 border-b border-white/5 pb-3 text-sm font-medium"><input className="accent-neon-cyan" type="checkbox" checked={selected.includes(index)} onChange={e => { setSelected(items => e.target.checked ? [...items, index].sort((a, b) => a-b) : items.filter(i => i !== index)); setReviewed(false); setKey(crypto.randomUUID()); }} />Inclure la séance {index + 1}</label>
        {current.sessions[index].ocr && <p className="text-warning-orange text-sm">Source reconnue par OCR — vérification visuelle requise.</p>}
        {!!current.sessions[index].batch_duplicates?.length && <p className="text-warning-orange text-sm">Même sport et date que les séances {current.sessions[index].batch_duplicates?.join(', ')} de ce lot. Vérifie qu’il ne s’agit pas de doublons.</p>}
        {current.sessions[index].duplicates.length > 0 && <p className="text-warning-orange text-sm">Séances du même sport déjà prévues ce jour : {current.sessions[index].duplicates.map(d => `#${d.id} ${d.description}`).join(', ')}.</p>}
        <label className="block text-xs text-text-secondary">Date<input aria-label={`Date séance ${index+1}`} className="mt-1.5 block w-full rounded-lg border border-white/10 bg-void/50 px-3 py-2.5 text-sm focus:border-neon-cyan/50 focus:outline-none" type="date" value={session.date ?? ''} onChange={e => patch(index, { date: e.target.value || null })} /></label>
        {session.date && <p className="text-xs text-text-muted">{new Date(`${session.date}T12:00:00`).toLocaleDateString('fr-FR', { dateStyle: 'long' })}</p>}
        <label className="block text-xs text-text-secondary">Description<input className="mt-1.5 block w-full rounded-lg border border-white/10 bg-void/50 px-3 py-2.5 text-sm focus:border-neon-cyan/50 focus:outline-none" value={session.description} maxLength={500} onChange={e => patch(index, { description: e.target.value })} /></label>
        <label className="block text-xs text-text-secondary">Sport<select className="mt-1.5 block w-full rounded-lg border border-white/10 bg-void/50 px-3 py-2.5 text-sm focus:border-neon-cyan/50 focus:outline-none" value={session.sport} onChange={e => patch(index, { sport: e.target.value })}>{[['running','Course'],['cycling','Vélo'],['swimming','Natation'],['strength','Musculation'],['walking','Marche'],['hiking','Randonnée'],['other','Autre']].map(([id,label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        {session.sport === 'strength' && <label className="block text-xs text-text-secondary">Texte de la séance (analysé par grammaire)<textarea className="mt-1.5 block w-full rounded-lg border border-white/10 bg-void/50 px-3 py-2.5 text-sm focus:border-neon-cyan/50 focus:outline-none" rows={4} value={session.strength_text} onChange={e => patch(index, { strength_text: e.target.value })} /></label>}
        {session.sport === 'strength' && <button className="text-neon-cyan text-xs" onClick={async () => {
          setBusy(true); setError('');
          try { const prescription = await documentRequest<Prescription>(`/agent/threads/${threadId}/imports/parse-strength`, { method: 'POST', body: JSON.stringify({ text: session.strength_text, date: session.date }) }); patch(index, { prescription }); }
          catch (err) { setError(err instanceof Error ? err.message : 'Lecture impossible.'); }
          finally { setBusy(false); }
        }}>Relire le texte de musculation et appliquer les séries reconnues</button>}
        <details className="rounded-lg border border-white/10 p-3"><summary className="cursor-pointer text-neon-cyan text-sm">Étapes et objectifs ({session.prescription.steps.length})</summary><PrescriptionEditor value={session.prescription} sport={session.sport} onChange={prescription => patch(index, { prescription })} /></details>
        <details open className="rounded-lg bg-void/40 p-3"><summary className="cursor-pointer text-xs font-medium text-text-muted">Sources à vérifier</summary>{session.provenance.map((source, i) => <blockquote key={i} className="mt-3 border-l-2 border-neon-cyan/20 pl-3 text-sm leading-relaxed"><p className="text-xs text-text-muted">{source.locator} · {current.sessions[index].sources[i]?.file_name ?? `document ${source.document_id.slice(0, 8)}`}</p><p className="whitespace-pre-wrap">{source.quote}</p></blockquote>)}</details>
        {session.uncertainties.length > 0 && <label className="block text-xs text-text-secondary">Points à résoudre (efface une ligne seulement après vérification)<textarea className="mt-1.5 block w-full rounded-lg border border-white/10 bg-void/50 px-3 py-2.5 text-sm focus:border-neon-cyan/50 focus:outline-none" value={session.uncertainties.join('\n')} onChange={e => patch(index, { uncertainties: e.target.value.split('\n').filter(Boolean) })} /></label>}
        {current.sessions[index].problems.map((problem, i) => <p key={i} className="text-danger-red text-sm">{problem}</p>)}
      </section>)}
      <button className="text-text-muted text-xs" onClick={async () => { setBusy(true); setError(''); try { await documentsApi.discard(threadId, current); await queryClient.invalidateQueries({ queryKey: ['coach-imports', threadId] }); onClose(); } catch (err) { setError(err instanceof Error ? err.message : 'Abandon impossible.'); } finally { setBusy(false); } }}>Abandonner ce brouillon et conserver les documents</button>
      {dirty && <button className="text-neon-cyan" onClick={save}>Enregistrer les corrections et revérifier</button>}
      <div className="sticky -bottom-6 -mx-6 space-y-3 border-t border-white/10 bg-abyss px-6 pb-6 pt-4 shadow-[0_-10px_25px_rgba(0,0,0,0.15)]">
      <label className="flex items-start gap-2.5 text-xs leading-relaxed text-text-secondary"><input className="mt-0.5 accent-neon-cyan" type="checkbox" checked={reviewed} disabled={dirty} onChange={e => setReviewed(e.target.checked)} />J’ai vérifié les sources, les dates, les unités et les doublons possibles.</label>
      {error && <p role="alert" className="text-danger-red">{error}</p>}
      <button className="flex w-full items-center justify-center gap-2 rounded-lg border border-neon-cyan/30 bg-neon-cyan/10 px-4 py-3 text-sm font-medium text-neon-cyan transition-colors hover:bg-neon-cyan/20 disabled:cursor-not-allowed disabled:opacity-40" disabled={busy || dirty || !reviewed || !selected.length || selected.some(i => current.sessions[i].problems.length > 0)} onClick={confirm}><ShieldCheck size={16} />{busy ? 'Enregistrement…' : `Ajouter ${selected.length} séance(s) au Planning`}</button>
      </div>
    </fieldset>
  </Modal>;
}

export function DocumentImports({ threadId }: { threadId: string }) {
  const drafts = useQuery({ queryKey: ['coach-imports', threadId], queryFn: () => documentsApi.drafts(threadId), retry: false });
  const [selected, setSelected] = useState<ImportDraft | null>(null);
  return <div className="space-y-2">
    {drafts.error && <p role="alert" className="text-danger-red text-xs">Imports indisponibles : {drafts.error.message}</p>}
    {drafts.data?.filter(draft => draft.status !== 'discarded').map(draft => <div key={draft.id} className="overflow-hidden rounded-xl border border-neon-cyan/15 bg-neon-cyan/[0.03] text-sm">
      {draft.status === 'confirmed' ? <Link to="/planning" className="flex items-center gap-3 p-4 text-success-green"><CalendarCheck2 size={18} className="shrink-0" /><span className="flex-1 text-xs leading-relaxed">{draft.session_ids.length} séance(s) ajoutée(s) — voir le Planning</span><ArrowRight size={14} /></Link> : <button className="flex w-full items-center gap-3 p-4 text-left transition-colors hover:bg-neon-cyan/5" onClick={() => setSelected(draft)}>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-neon-cyan/10 text-neon-cyan"><ClipboardList size={18} /></span>
        <span className="min-w-0 flex-1"><span className="mb-1 block text-[10px] uppercase tracking-wider text-text-muted">Import à valider</span><span className="block text-xs leading-relaxed text-neon-cyan">Vérifier {draft.sessions.length} séance(s) avant ajout au Planning</span></span><ArrowRight size={15} className="shrink-0 text-neon-cyan/70" />
      </button>}
    </div>)}
    {selected && <DraftEditor threadId={threadId} draft={selected} onClose={() => setSelected(null)} />}
  </div>;
}
