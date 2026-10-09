import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDownToLine, Check, FileText, Image, LoaderCircle, Paperclip, Plus, Sheet, Trash2, UploadCloud } from 'lucide-react';
import { ACCEPTED_FILES, documentsApi, downloadDocument, uploadDocument, type CoachDocument } from '@/lib/documents';
import { DocumentPreview } from './DocumentPreview';

export interface AttachmentsHandle { upload: (files: File[]) => void }

export function DocumentAttachments({ threadId, disabled = false, compact = false, ref, onBusy, onDocuments }: { threadId: string; disabled?: boolean; compact?: boolean; ref: Ref<AttachmentsHandle>; onBusy: (busy: boolean) => void; onDocuments: (ids: string[]) => void }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['coach-documents', threadId], queryFn: () => documentsApi.list(threadId), retry: false });
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [source, setSource] = useState<CoachDocument | null>(null);
  useEffect(() => () => { controller.current?.abort(); onBusy(false); }, [onBusy]);
  useEffect(() => { if (query.data) onDocuments(query.data.map(doc => doc.id)); }, [query.data, onDocuments]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['coach-documents', threadId] });
  const upload = async (files: File[]) => {
    if (disabled || controller.current || !files.length) return;
    if (files.length > 5) { setErrors(['Maximum 5 fichiers par dépôt.']); return; }
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); onBusy(true); setErrors([]);
    try {
      for (const file of files) {
        if (abort.signal.aborted) break;
        try { await uploadDocument(threadId, file, abort.signal, message => setProgress(`${file.name} · ${message}`)); }
        catch (error) { setErrors(previous => [...previous, `${file.name} : ${abort.signal.aborted ? 'Envoi annulé. Supprime le fichier incomplet avant de le renvoyer.' : error instanceof Error ? error.message : 'Envoi impossible.'}`]); }
      }
    } finally {
      controller.current = null; setBusy(false); onBusy(false); setProgress(''); await refresh();
    }
  };
  useImperativeHandle(ref, () => ({ upload: files => { void upload(files); } }));
  const action = async (work: () => Promise<unknown>) => {
    try { await work(); } catch (error) { setErrors(previous => [...previous.slice(-19), error instanceof Error ? error.message : 'Opération impossible.']); }
  };
  const hasDocuments = !!query.data?.length;
  return <section aria-label="Documents du coach" className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.015] text-xs">
    <input ref={input} type="file" multiple accept={ACCEPTED_FILES} className="sr-only" aria-label="Joindre des documents" disabled={busy || disabled} onChange={e => { void upload(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
    <div className="flex items-center justify-between gap-3 px-3.5 py-3">
      <span className="flex items-center gap-2 font-medium text-text-secondary"><Paperclip size={14} className="text-text-muted" />Documents{hasDocuments && <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] tabular-nums text-text-muted">{query.data?.length}</span>}</span>
      <button disabled={busy || disabled} onClick={() => input.current?.click()} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-neon-cyan transition-colors hover:bg-neon-cyan/10 disabled:opacity-40"><Plus size={13} />Joindre</button>
    </div>
    {!hasDocuments && !busy && !compact && <button disabled={disabled} onClick={() => input.current?.click()} className="mx-3 mb-3 flex w-[calc(100%-1.5rem)] flex-col items-center gap-2 rounded-lg border border-dashed border-white/10 px-4 py-5 transition-colors hover:border-neon-cyan/30 hover:bg-neon-cyan/[0.03] disabled:opacity-50">
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
