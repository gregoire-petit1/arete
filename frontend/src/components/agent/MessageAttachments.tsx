import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileText } from 'lucide-react';
import { documentsApi, type CoachDocument } from '@/lib/documents';
import { DocumentPreview } from './DocumentPreview';

export function MessageAttachments({
  ids,
  threadId,
}: {
  ids: string[];
  threadId: string;
}) {
  const docs = useQuery({
    queryKey: ['coach-documents', threadId],
    queryFn: () => documentsApi.list(threadId),
    retry: false,
  });
  const [selected, setSelected] = useState<CoachDocument | null>(null);
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {ids.map((id) => {
        const doc = docs.data?.find((d) => d.id === id);
        return (
          <button
            key={id}
            disabled={!doc || doc.status !== 'ready'}
            onClick={() => doc && setSelected(doc)}
            className="flex min-h-11 max-w-full items-center gap-2 rounded-lg border border-text-muted/20 bg-abyss px-3 text-xs"
          >
            <FileText size={16} className="shrink-0" />
            <span className="truncate">
              {doc?.name ??
                (docs.isPending
                  ? 'Chargement du fichier…'
                  : 'Document indisponible')}
            </span>
          </button>
        );
      })}
      {selected && (
        <DocumentPreview
          threadId={threadId}
          document={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
