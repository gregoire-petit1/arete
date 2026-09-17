import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Sparkles } from 'lucide-react';
import { FitDropzone } from '@/components';
import { Button, Panel } from '@/components/ui';
import { ManualCardioModal } from './ManualCardioModal';
import { garminApi, tipsApi } from '@/lib/api';
import { RecentSessions } from './RecentSessions';
import { invalidateAfterSession } from '@/lib/queryKeys';

interface Upload {
  filename: string;
  status: 'success' | 'error' | 'uploading';
  message?: string;
}

/** "API Error 400: {"detail":"..."}" -> "..." */
function readableError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  const match = raw.match(/\{.*\}/s);
  if (match) {
    try {
      const body = JSON.parse(match[0]) as { detail?: string };
      if (body.detail) return body.detail;
    } catch {
      // fall through to the raw message
    }
  }
  return raw;
}

export function CardioTab() {
  const queryClient = useQueryClient();
  const [recentUploads, setRecentUploads] = useState<Upload[]>([]);
  const [feedback, setFeedback] = useState<{ feedback: string; highlights: string[] } | null>(null);
  const [feedbackError, setFeedbackError] = useState(false);
  const [showManual, setShowManual] = useState(false);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      setRecentUploads((prev) => [{ filename: file.name, status: 'uploading' }, ...prev]);
      try {
        return await garminApi.uploadFit(file);
      } finally {
        setRecentUploads((prev) => prev.filter((u) => u.status !== 'uploading'));
      }
    },
    onSuccess: async (result) => {
      setRecentUploads((prev) => [
        { filename: result.filename || 'activity.fit', status: 'success', message: 'Uploaded' },
        ...prev,
      ]);
      invalidateAfterSession(queryClient);
      if (result.activity_id) {
        try {
          setFeedback(await tipsApi.getPostSession('cardio', result.activity_id));
          setFeedbackError(false);
        } catch {
          setFeedbackError(true); // best-effort, but say so
        }
      }
    },
    onError: (error) => {
      setRecentUploads((prev) => [
        { filename: 'upload', status: 'error', message: readableError(error) },
        ...prev,
      ]);
    },
  });

  return (
    <div className="space-y-4 sm:space-y-8">
      <Panel
        title={
          <span className="flex items-center justify-between gap-2 w-full">
            IMPORTER UNE SÉANCE CARDIO
            <Button variant="ghost" onClick={() => setShowManual(true)}>
              <Plus className="w-4 h-4" />
              SANS MONTRE
            </Button>
          </span>
        }
        animate={false}
      >
        <FitDropzone
          onUpload={async (file) => uploadMutation.mutate(file)}
          isUploading={uploadMutation.isPending}
          recentUploads={recentUploads}
        />
      </Panel>

      {feedback && (
        <Panel
          title={
            <span className="flex items-center gap-2">
              <Sparkles className="w-4 h-4" />
              ANALYSE IA
            </span>
          }
          titleTone="text-neon-cyan"
        >
          <p className="text-sm font-mono text-text-secondary mb-3">{feedback.feedback}</p>
          {feedback.highlights.length > 0 && (
            <ul className="space-y-1">
              {feedback.highlights.map((h, i) => (
                <li key={i} className="text-xs font-mono text-text-muted flex items-start gap-2">
                  <span className="text-neon-cyan mt-0.5">▸</span>
                  {h}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      {feedbackError && (
        <p className="text-xs font-mono text-text-muted">Analyse IA indisponible pour cette séance.</p>
      )}

      <RecentSessions />
      <ManualCardioModal open={showManual} onClose={() => setShowManual(false)} />
    </div>
  );
}
