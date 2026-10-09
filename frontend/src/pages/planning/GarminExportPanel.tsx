import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { PlannedSession } from '@/types';
import { exportApi } from '@/lib/documents';
import { qk } from '@/lib/queryKeys';
import { PrescriptionEditor } from '@/components/PrescriptionEditor';
import { Modal, ModalHeader } from '@/components/ui';

const labels: Record<string, string> = { scheduled: 'Programmé dans Garmin Connect', transfer_requested: 'Transfert demandé — synchronise la montre', working: 'Synchronisation en cours', dirty: 'À resynchroniser', pending_removal: 'Retrait Garmin à effectuer', uncertain: 'Résultat indéterminé — vérifier Garmin', conflict: 'Conflit avec Garmin Connect', failed: 'Échec — consulter le détail', ready: 'Vérifié — prêt à poursuivre', removed: 'Retiré de Garmin Connect' };

function EditSession({ session, onClose }: { session: PlannedSession; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [date, setDate] = useState(session.date);
  const [description, setDescription] = useState(session.description ?? '');
  const [prescription, setPrescription] = useState(session.prescription ?? { version: 1 as const, steps: [] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const save = async () => {
    setBusy(true); setError('');
    try {
      await exportApi.update(session.id, session.revision ?? 1, date, description, prescription);
      await Promise.all([queryClient.invalidateQueries({ queryKey: qk.planned() }), queryClient.invalidateQueries({ queryKey: ['garmin-exports'] })]);
      onClose();
    } catch (error) { setError(error instanceof Error ? error.message : 'Modification impossible.'); }
    finally { setBusy(false); }
  };
  return <Modal open onClose={() => { if (!busy) onClose(); }} className="max-w-xl max-h-[90dvh] overflow-y-auto">
    <ModalHeader title="Séance structurée" onClose={onClose} />
    <fieldset disabled={busy} className="space-y-3 mt-3">
      <label className="block text-sm">Date<input type="date" className="block bg-void border p-2 rounded" value={date} onChange={e => setDate(e.target.value)} /></label>
      {date && <p className="text-xs text-text-muted">{new Date(`${date}T12:00:00`).toLocaleDateString('fr-FR', { dateStyle: 'long' })}</p>}
      <label className="block text-sm">Description<input className="block w-full bg-void border p-2 rounded" maxLength={500} value={description} onChange={e => setDescription(e.target.value)} /></label>
      <PrescriptionEditor sport={session.sport} value={prescription} onChange={setPrescription} />
      {error && <p role="alert" className="text-danger-red">{error}</p>}
      <p className="text-xs text-text-muted">Une modification reste locale jusqu’au prochain envoi explicite vers Garmin.</p>
      <button className="text-neon-cyan" onClick={save} disabled={busy || !date || !description || !prescription.steps.length}>{busy ? 'Enregistrement…' : 'Enregistrer'}</button>
    </fieldset>
  </Modal>;
}

export function GarminExportPanel({ sessions }: { sessions: PlannedSession[] }) {
  const queryClient = useQueryClient();
  const statuses = useQuery({ queryKey: ['garmin-exports'], queryFn: exportApi.statuses, retry: false });
  const [open, setOpen] = useState(false);
  const devices = useQuery({ queryKey: ['garmin-workout-devices'], queryFn: exportApi.devices, enabled: open, retry: false });
  const [deviceId, setDeviceId] = useState<number | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [editing, setEditing] = useState<PlannedSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const byId = new Map(statuses.data?.map(status => [status.session_id, status]));
  const visibleIds = new Set(sessions.map(s => s.id));
  const effectiveSelection = selected.filter(id => visibleIds.has(id));
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['garmin-exports'] });
  const run = async (work: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true); setError('');
    try { await work(); }
    catch (error) { setError(error instanceof Error ? error.message : 'Opération impossible.'); }
    finally { setBusy(false); setProgress(''); await refresh(); }
  };
  const send = () => run(async () => {
    if (effectiveSelection.length > 50) throw new Error('Maximum 50 séances par envoi.');
    for (const [index, id] of effectiveSelection.entries()) {
      setProgress(`Séance ${index+1}/${effectiveSelection.length}…`);
      const result = await exportApi.export(id, deviceId);
      await refresh();
      if (!['scheduled', 'transfer_requested'].includes(result.state)) throw new Error(result.error ?? 'L’envoi s’est arrêté. Vérifie l’état de la séance.');
    }
    setSelected([]); setReviewed(false);
  });
  return <section className="mb-6 rounded border border-text-muted/20 p-4 space-y-3" aria-label="Envoi des séances vers Garmin">
    <button className="text-neon-cyan" onClick={() => setOpen(!open)}>Séances structurées et Garmin Connect</button>
    {statuses.error && <p role="alert" className="text-danger-red">{statuses.error.message}</p>}
    {open && <fieldset disabled={busy} className="space-y-3">
      <p className="text-sm text-text-muted">Sélectionne les séances de cette semaine. Elles seront programmées aux mêmes dates dans Garmin Connect.</p>
      {sessions.map(session => <div key={session.id} className="rounded border border-text-muted/20 p-3 space-y-1 text-sm">
        <label className="flex gap-2"><input type="checkbox" disabled={!session.prescription} checked={effectiveSelection.includes(session.id)} onChange={e => { setSelected(ids => e.target.checked ? [...ids, session.id] : ids.filter(id => id !== session.id)); setReviewed(false); }} />{session.date} · {session.description || session.sport}</label>
        <button className="text-neon-cyan text-xs" onClick={() => setEditing(session)}>{session.prescription ? 'Voir ou modifier les étapes' : 'Définir les étapes avant export'}</button>
        {byId.has(session.id) && <><p>{labels[byId.get(session.id)!.state] ?? byId.get(session.id)!.state}</p>{byId.get(session.id)!.error && <p className="text-danger-red">{byId.get(session.id)!.error}</p>}<button className="underline text-xs" onClick={() => run(() => exportApi.reconcile(session.id))}>Vérifier Garmin</button></>}
      </div>)}
      <label className="block text-sm">Destination<select className="block bg-void border p-2 rounded w-full" value={deviceId ?? ''} onChange={e => { setDeviceId(e.target.value ? Number(e.target.value) : null); setReviewed(false); }}><option value="">Garmin Connect uniquement</option>{devices.data?.map(device => <option key={device.id} value={device.id} disabled={!device.sports.length}>{device.name}{device.sports.length ? '' : ' — compatibilité à vérifier dans Connect'}</option>)}</select></label>
      {devices.error && <p role="alert" className="text-warning-orange">Appareils indisponibles : {devices.error.message}</p>}
      <p className="text-xs text-text-muted">L’application confirme la programmation et la demande de transfert. La réception sur la montre se vérifie après sa synchronisation avec Garmin Connect.</p>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />J’ai vérifié les dates et le contenu des séances sélectionnées.</label>
      <button className="rounded bg-neon-cyan/20 p-3 disabled:opacity-40" disabled={busy || !reviewed || !effectiveSelection.length} onClick={send}>Envoyer {effectiveSelection.length} séance(s) vers Garmin</button>
      {statuses.data?.filter(status => status.deleted && status.state !== 'removed').map(status => <div key={status.session_id} className="border border-warning-orange/30 p-3 text-sm"><p>Séance supprimée #{status.session_id} · {labels[status.state]}</p>{status.error && <p className="text-danger-red">{status.error}</p>}<button className="underline mr-3" onClick={() => run(() => exportApi.reconcile(status.session_id))}>Vérifier Garmin</button><button className="text-danger-red" onClick={() => run(() => exportApi.remove(status.session_id))}>Retirer de Garmin Connect</button></div>)}
    </fieldset>}
    {busy && <p role="status">{progress || 'Opération en cours…'} Fermer la page n’annule pas une écriture déjà transmise.</p>}
    {error && <p role="alert" className="text-danger-red">{error}</p>}
    {editing && <EditSession key={editing.id} session={editing} onClose={() => setEditing(null)} />}
  </section>;
}
