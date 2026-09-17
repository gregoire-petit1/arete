import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { FitDropzone } from '@/components';
import { Panel } from '@/components/ui';
import { garminApi, tipsApi } from '@/lib/api';
import { RecentSessions } from './RecentSessions';
import { invalidateAfterSession } from '@/lib/queryKeys';

interface Upload {
  filename: string;
  status: 'success' | 'error' | 'uploading';
  message?: string;
}

export function CardioTab() {
  const queryClient = useQueryClient();
  const [recentUploads, setRecentUploads] = useState<Upload[]>([]);
  const [feedback, setFeedback] = useState<{ feedback: string; highlights: string[] } | null>(null);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => garminApi.uploadFit(file),
    onSuccess: async (result) => {
      setRecentUploads((prev) => [
        { filename: result.filename || 'activity.fit', status: 'success', message: 'Uploaded' },
        ...prev,
      ]);
      invalidateAfterSession(queryClient);
      if (result.activity_id) {
        try {
          setFeedback(await tipsApi.getPostSession('cardio', result.activity_id));
        } catch {
          // AI feedback is best-effort
        }
      }
    },
    onError: (error) => {
      setRecentUploads((prev) => [{ filename: 'upload', status: 'error', message: String(error) }, ...prev]);
    },
  });

  return (
    <div className="space-y-4 sm:space-y-8">
      <Panel title="UPLOAD CARDIO SESSION" animate={false}>
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
              AI ANALYSIS
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

      <RecentSessions />
    </div>
  );
}
