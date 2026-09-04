import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, LogOut, Target, Watch } from 'lucide-react';
import { cn } from '@/lib/utils';
import { garminApi, stravaApi } from '@/lib/api';
import { Button } from '@/components/ui';

export function ConnectionsTab() {
  const queryClient = useQueryClient();
  const [syncResult, setSyncResult] = useState<string | null>(null);

  const { data: syncStatus } = useQuery({
    queryKey: ['syncStatus'],
    queryFn: garminApi.getSyncStatus,
    retry: false,
  });

  const { data: stravaStatus, isError: stravaError } = useQuery({
    queryKey: ['stravaStatus'],
    queryFn: stravaApi.getStatus,
    retry: false,
  });

  // Coming back from the Strava OAuth redirect: clean the URL and refresh the status.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('strava') === 'connected') {
      window.history.replaceState({}, '', window.location.pathname);
      queryClient.invalidateQueries({ queryKey: ['stravaStatus'] });
    }
  }, [queryClient]);

  const connectMutation = useMutation({
    mutationFn: stravaApi.getAuthorizeUrl,
    onSuccess: ({ url }) => {
      window.location.href = url;
    },
    onError: (err) =>
      setSyncResult(`Strava: ${err instanceof Error ? err.message : 'could not start authorization'}`),
  });

  const syncMutation = useMutation({
    mutationFn: () => stravaApi.sync(30),
    onSuccess: (result) => {
      setSyncResult(`${result.imported} imported, ${result.skipped} skipped`);
      queryClient.invalidateQueries({ queryKey: ['stravaStatus'] });
      queryClient.invalidateQueries({ queryKey: ['actual'] });
    },
    onError: (err) => setSyncResult(`Sync failed: ${err instanceof Error ? err.message : err}`),
  });

  const disconnectMutation = useMutation({
    mutationFn: stravaApi.disconnect,
    onSuccess: () => {
      setSyncResult(null);
      queryClient.invalidateQueries({ queryKey: ['stravaStatus'] });
    },
    onError: () => setSyncResult('Disconnect failed'),
  });

  const garminConnected = syncStatus?.garmin_authenticated;
  const stravaConnected = stravaStatus?.connected ?? false;

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-sans text-text-primary mb-4">CONNECTED SERVICES</h2>

      <div className="space-y-3">
        {/* Garmin */}
        <div
          className={cn(
            'flex items-center gap-4 p-4 rounded bg-abyss/50 border',
            garminConnected ? 'border-success-green/30' : 'border-text-muted/20'
          )}
        >
          <Watch className="w-6 h-6 text-text-muted" />
          <div className="flex-1">
            <div className="font-mono text-sm text-text-primary">Garmin Connect</div>
            {syncStatus?.user_email && (
              <div className="text-xs text-neon-cyan">{syncStatus.user_email}</div>
            )}
          </div>
          {garminConnected ? (
            <div className="flex items-center gap-1 text-xs text-success-green">
              <Check className="w-4 h-4" />
              Connected
            </div>
          ) : (
            <span className="text-xs font-mono text-text-muted">Not connected</span>
          )}
        </div>

        {/* Strava */}
        <div
          className={cn(
            'flex items-center gap-4 p-4 rounded bg-abyss/50 border',
            stravaConnected ? 'border-success-green/30' : 'border-text-muted/20'
          )}
        >
          <Target className="w-6 h-6 text-text-muted" />
          <div className="flex-1">
            <div className="font-mono text-sm text-text-primary">Strava</div>
            {stravaConnected && stravaStatus?.athlete_name && (
              <div className="text-xs text-strava">{stravaStatus.athlete_name}</div>
            )}
            {stravaError && (
              <div className="text-xs text-danger-red mt-1 font-mono">Status unavailable</div>
            )}
            {syncResult && (
              <div className="text-xs text-text-muted mt-1 font-mono">{syncResult}</div>
            )}
          </div>
          {stravaConnected ? (
            <div className="flex items-center gap-2">
              <Button
                variant="strava"
                size="sm"
                loading={syncMutation.isPending}
                onClick={() => {
                  setSyncResult(null);
                  syncMutation.mutate();
                }}
              >
                {syncMutation.isPending ? 'SYNCING...' : 'SYNC NOW'}
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => disconnectMutation.mutate()}
                loading={disconnectMutation.isPending}
                aria-label="Disconnect Strava"
              >
                <LogOut className="w-3 h-3" />
              </Button>
            </div>
          ) : (
            <Button
              variant="strava"
              size="sm"
              onClick={() => connectMutation.mutate()}
              loading={connectMutation.isPending}
            >
              CONNECT
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
