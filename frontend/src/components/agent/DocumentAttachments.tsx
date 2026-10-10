import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDownToLine, Check, FileText, Image, LoaderCircle, Paperclip, Plus, Sheet, Trash2, UploadCloud } from 'lucide-react';
import { ACCEPTED_FILES, documentsApi, downloadDocument, uploadDocument, type CoachDocument } from '@/lib/documents';
import { DocumentPreview } from './DocumentPreview';

export interface AttachmentsHandle { choose: () => void; upload: (files: File[]) => void }

export function DocumentAttachments({ threadId, disabled = false, ref, onBusy, onDocuments, compact = false, collapsed = false, selectedIds = [] }: { threadId: string; disabled?: boolean; ref: Ref<AttachmentsHandle>; onBusy: (busy: boolean) => void; onDocuments: (ids: string[]) => void; compact?: boolean; collapsed?: boolean; selectedIds?: string[] }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['coach-documents', threadId], queryFn: () => documentsApi.list(threadId), retry: false });
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [library, setLibrary] = useState(false);
  const [source, setSource] = useState<CoachDocument | null>(null);
  useEffect(() => () => { controller.current?.abort(); onBusy(false); }, [onBusy]);
  useEffect(() => { if (!compact && query.data) onDocuments(query.data.map(doc => doc.id)); }, [query.data, onDocuments, compact]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['coach-documents', threadId] });
  const upload = async (files: File[]) => {
    if (disabled || controller.current || !files.length) return;
    if (files.length > 5) { setErrors(['Maximum 5 fichiers par dépôt.']); return; }
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); onBusy(true); setErrors([]);
    const selected = [...selectedIds];
    try {
      for (const file of files) {
        if (abort.signal.aborted) break;
        try {
          const doc = await uploadDocument(threadId, file, abort.signal, message => setProgress(`${file.name} · ${message}`));
          if (compact && !selected.includes(doc.id)) { selected.push(doc.id); onDocuments([...selected]); }
        }
        catch (error) { setErrors(previous => [...previous, `${file.name} : ${abort.signal.aborted ? 'Envoi annulé. Supprime le fichier incomplet avant de le renvoyer.' : error instanceof Error ? error.message : 'Envoi impossible.'}`]); }
      }
    } finally {
      // Keep Send blocked until the library includes the finalized extraction.
      try { await refresh(); }
      finally { controller.current = null; setBusy(false); onBusy(false); setProgress(''); }
    }
  };
  useImperativeHandle(ref, () => ({ choose: () => input.current?.click(), upload: files => { void upload(files); } }));
  const action = async (work: () => Promise<unknown>) => {
    try { await work(); } catch (error) { setErrors(previous => [...previous.slice(-19), error instanceof Error ? error.message : 'Opération impossible.']); }
  };
  const hasDocuments = !!query.data?.length;
  if (compact) return <div className="contents text-xs">
    <input ref={input} type="file" multiple accept={ACCEPTED_FILES} className="sr-only" aria-label="Joindre des documents" disabled={busy || disabled} onChange={e => { void upload(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
    {selectedIds.length > 0 && <div className="col-span-full row-start-1 mb-2 flex min-w-0 flex-wrap gap-2 max-h-44 overflow-y-auto" aria-label="Pièces jointes du brouillon">
      {selectedIds.map(id => {
        const doc = query.data?.find(d => d.id === id);
        return <div key={id} className="flex min-w-0 max-w-full items-center rounded-lg bg-text-muted/5 pl-2">
          <button disabled={!doc || doc.status !== 'ready'} onClick={() => doc && setSource(doc)} title={doc?.status === 'ready' ? 'Ouvrir l’aperçu' : 'À vérifier ou retirer'} aria-label={`Consulter ${doc?.name ?? 'le document'}`} className="min-w-0 min-h-8 text-left flex items-center gap-2"><FileText size={14} className="shrink-0 text-text-muted" /><span className="max-w-48 truncate">{doc?.name ?? 'Document indisponible'}{doc && doc.status !== 'ready' && ' · Incomplet'}</span></button>
          <button disabled={busy || disabled} aria-label={`Retirer ${doc?.name ?? 'le document'} du brouillon`} onClick={() => onDocuments(selectedIds.filter(key => key !== id))} className="size-8 shrink-0 rounded-lg text-text-muted hover:bg-text-muted/10">×</button>
        </div>;
      })}
    </div>}
    {hasDocuments && <button aria-label={`Fichiers du fil (${query.data?.length})`} title="Fichiers de cette conversation" aria-expanded={library} onClick={() => setLibrary(!library)} className="col-start-3 row-start-2 flex h-8 shrink-0 items-center gap-1 rounded-lg px-1 text-text-muted hover:text-text-primary focus-visible:outline-2 focus-visible:outline-neon-cyan"><Paperclip size={14} aria-hidden="true" /><span className="text-[11px] tabular-nums">{query.data?.length}</span></button>}
    {(busy || query.error || errors.length > 0 || (library && hasDocuments)) && <div className="col-span-full row-start-3 mt-2 flex min-w-0 flex-col gap-2">
      {busy && <div role="status" aria-live="polite" className="flex items-center gap-2 py-2 text-text-secondary"><LoaderCircle size={14} className="animate-spin" /><span className="min-w-0 flex-1 break-words">{progress || 'Préparation…'}</span><button className="min-h-11" onClick={() => controller.current?.abort()}>Annuler</button></div>}
      {query.error && <p role="alert" className="text-danger-red">{query.error.message}</p>}
      {errors.map((error, i) => <p role="alert" key={i} className="text-danger-red break-words">{error}</p>)}
      {library && hasDocuments && <div className="max-h-48 overflow-y-auto rounded-lg border border-text-muted/20 p-3 space-y-2">
        <p className="text-text-muted">Sélectionne les fichiers du prochain message. Retirer du brouillon conserve l’original.</p>
        {query.data?.map(doc => <div key={doc.id} className="flex items-center gap-2"><label className="min-w-0 flex-1 flex gap-2 py-2"><input type="checkbox" disabled={busy || disabled || doc.status !== 'ready'} checked={selectedIds.includes(doc.id)} onChange={e => onDocuments(e.target.checked ? [...selectedIds, doc.id] : selectedIds.filter(id => id !== doc.id))} /><span className="truncate">{doc.name}{doc.status !== 'ready' && ' · Incomplet'}</span></label><button aria-label={`Supprimer définitivement ${doc.name}`} className="size-11 text-danger-red" disabled={busy || disabled} onClick={() => action(async () => { await documentsApi.delete(threadId, doc.id); onDocuments(selectedIds.filter(id => id !== doc.id)); await refresh(); })}><Trash2 size={16} /></button></div>)}
      </div>}
    </div>}
    {source && <DocumentPreview threadId={threadId} document={source} onClose={() => setSource(null)} />}
  </div>;
  return <section aria-label="Documents du coach" className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.015] text-xs">
    <input ref={input} type="file" multiple accept={ACCEPTED_FILES} className="sr-only" aria-label="Joindre des documents" disabled={busy || disabled} onChange={e => { void upload(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
    <div className="flex items-center justify-between gap-3 px-3.5 py-3">
      <span className="flex items-center gap-2 font-medium text-text-secondary"><Paperclip size={14} className="text-text-muted" />Documents{hasDocuments && <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] tabular-nums text-text-muted">{query.data?.length}</span>}</span>
      <button disabled={busy || disabled} onClick={() => input.current?.click()} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-neon-cyan transition-colors hover:bg-neon-cyan/10 disabled:opacity-40"><Plus size={13} />Joindre</button>
    </div>
    {!hasDocuments && !busy && !collapsed && <button disabled={disabled} onClick={() => input.current?.click()} className="mx-3 mb-3 flex w-[calc(100%-1.5rem)] flex-col items-center gap-2 rounded-lg border border-dashed border-white/10 px-4 py-5 transition-colors hover:border-neon-cyan/30 hover:bg-neon-cyan/[0.03] disabled:opacity-50">
      <UploadCloud size={23} strokeWidth={1.5} className="mb-1 text-neon-cyan/70" />
      <span className="text-text-secondary">Dépose ton programme ici</span>
      <span className="text-[10px] leading-relaxed text-text-muted">Excel, PDF, images, texte · 20 Mio par fichier</span>
    </button>}
    {busy && <div role="status" className="mx-3 mb-3 rounded-lg border border-neon-cyan/15 bg-neon-cyan/5 p-3">
      <div className="flex items-start gap-2"><LoaderCircle size={14} className="mt-0.5 shrink-0 animate-spin text-neon-cyan" /><span className="min-w-0 flex-1 break-words leading-relaxed text-text-secondary">{progress || 'Préparation du document…'}</span><button className="text-[10px] text-text-muted hover:text-text-primary" onClick={() => controller.current?.abort()}>Annuler</button></div>
    </div>}
    {query.error && <p role="alert" className="px-3 pb-3 leading-relaxed text-danger-red">Documents indisponibles : {query.error.message}</p>}
    {errors.map((error, index) => <p role="alert" key={index} className="mx-3 mb-3 rounded-lg bg-danger-red/5 p-3 leading-relaxed text-danger-red">{error}</p>)}
    {hasDocuments && <ul className="max-h-64 space-y-1 overflow-y-auto px-2 pb-2">{query.data?.map(doc => {
      const Icon = /\.(png|jpe?g|webp)$/i.test(doc.name) ? Image : /\.(xlsx?|csv)$/i.test(doc.name) ? Sheet : FileText;
      return <li key={doc.id} className="group flex items-center gap-2 rounded-lg border border-transparent px-2 py-2 transition-colors hover:border-white/5 hover:bg-white/[0.03]">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/[0.04] text-text-muted"><Icon size={17} strokeWidth={1.5} /></div>
        <button disabled={doc.status !== 'ready'} aria-label={`Consulter ${doc.name}`} onClick={() => setSource(doc)} className="min-w-0 flex-1 text-left disabled:cursor-default">
          <span className="block truncate font-medium text-text-secondary group-hover:text-text-primary" title={doc.name}>{doc.name}</span>
          <span className="mt-1 flex items-center gap-2 text-[10px] text-text-muted"><span>{doc.size < 1024 * 1024 ? `${Math.max(1, Math.round(doc.size / 1024))} Ko` : `${(doc.size / 1024 / 1024).toFixed(1)} Mio`}</span><span className="h-0.5 w-0.5 rounded-full bg-text-muted/40" /><span className={doc.status === 'ready' ? 'inline-flex items-center gap-1 text-success-green/80' : 'text-warning-orange'}>{doc.status === 'ready' && <Check size={10} />}{doc.status === 'ready' ? 'Prêt' : 'Incomplet'}</span></span>
        </button>
        {doc.status === 'ready' && <button aria-label={`Télécharger ${doc.name}`} title="Télécharger l’original" className="rounded-md p-1.5 text-text-muted/60 hover:bg-white/5 hover:text-text-primary" onClick={() => action(() => downloadDocument(threadId, doc))}><ArrowDownToLine size={14} /></button>}
        <button disabled={busy || disabled} aria-label={`Supprimer ${doc.name}`} title="Supprimer le document" className="rounded-md p-1.5 text-text-muted/60 hover:bg-danger-red/10 hover:text-danger-red disabled:opacity-30" onClick={() => action(async () => { await documentsApi.delete(threadId, doc.id); await refresh(); })}><Trash2 size={14} /></button>
      </li>;
    })}</ul>}
    {source && <DocumentPreview threadId={threadId} document={source} onClose={() => setSource(null)} />}
  </section>;
}
