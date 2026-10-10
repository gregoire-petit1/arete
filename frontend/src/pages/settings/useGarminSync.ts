import { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { streamGarminSync, type SyncOptions, type SyncProgress } from '@/lib/garminSync';
import { invalidateAfterSession } from '@/lib/queryKeys';

export function useGarminSync() {
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<SyncProgress | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const mutation = useMutation({
    mutationFn: async (options: SyncOptions) => {
      controller.current = new AbortController();
      setProgress({ stage: 'preparing', completed: 0, total: null, activity_name: null });
      return streamGarminSync(options, setProgress, controller.current.signal);
    },
    retry: false,
    // A failed connection can still have committed sessions: refresh in both cases.
    onSettled: () => {
      controller.current = null;
      queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      invalidateAfterSession(queryClient);
    },
  });
  return { ...mutation, progress };
}
