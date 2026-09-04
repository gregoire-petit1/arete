import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle, Cloud, Database, LogOut, RefreshCw, Server, XCircle } from 'lucide-react';
import { GarminLoginModal, SystemAlert } from '@/components';
import { Button, Panel } from '@/components/ui';
import { garminApi, garminHealthApi, healthApi } from '@/lib/api';
import { StatusRow } from './StatusRow';
import { SyncOptionsForm, type SyncOptions } from './SyncOptionsForm';

type Alert = { type: 'success' | 'error'; message: string };

export function SystemTab() {
  const queryClient = useQueryClient();
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [alert, setAlert] = useState<Alert | null>(null);

  const { data: health, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.check,
    retry: false,
  });

  const { data: syncStatus, isLoading: syncLoading, refetch: refetchSync } = useQuery({
    queryKey: ['syncStatus'],
    queryFn: garminApi.getSyncStatus,
    refetchInterval: 30000,
    retry: false,
  });

  const { data: healthStatus } = useQuery({
    queryKey: ['garminHealthStatus'],
    queryFn: garminHealthApi.getStatus,
    retry: false,
  });

  const logoutMutation = useMutation({
    mutationFn: garminApi.logout,
    onSuccess: () => {
      setAlert({ type: 'success', message: 'LOGGED OUT' });
      queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: (options: SyncOptions) => garminApi.syncActivities(options),
    onSuccess: (result) => {
      setAlert({ type: 'success', message: `SYNCED ${result.synced} ACTIVITIES` });
      queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
      queryClient.invalidateQueries({ queryKey: ['actual'] });
    },
    onError: (error) => setAlert({ type: 'error', message: `SYNC FAILED: ${error}` }),
  });

  const healthSyncMutation = useMutation({
    mutationFn: () => {
      const end = new Date();
      const start = new Date(end.getTime() - 7 * 86400000);
      return garminHealthApi.sync(start.toISOString().slice(0, 10), end.toISOString().slice(0, 10));
    },
    onSuccess: (result) => {
      setAlert({
        type: result.days_failed ? 'error' : 'success',
        message: `HEALTH: ${result.days_synced} DAYS SYNCED${result.days_failed ? `, ${result.days_failed} FAILED` : ''}`,
      });
      queryClient.invalidateQueries({ queryKey: ['garminHealthStatus'] });
      queryClient.invalidateQueries({ queryKey: ['garmin-health'] });
    },
    onError: (error) => setAlert({ type: 'error', message: `HEALTH SYNC FAILED: ${error}` }),
  });

  const handleRefresh = () => {
    refetchHealth();
    refetchSync();
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-sans text-text-primary">SYSTEM</h2>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          className="text-text-secondary hover:border-neon-cyan/50 hover:text-neon-cyan"
        >
          <RefreshCw className="w-3 h-3" />
          REFRESH
        </Button>
      </div>

      {alert && (
        <div className="animate-fade-down">
          <SystemAlert type={alert.type} message={alert.message} onDismiss={() => setAlert(null)} />
        </div>
      )}

      <Panel variant="inset" title="STATUS">
        <div className="space-y-2">
          <StatusRow
            icon={<Server className="w-4 h-4" />}
            label="API Health"
            status={health?.status === 'ok' ? 'online' : healthLoading ? 'loading' : 'offline'}
          />
          <StatusRow
            icon={<Database className="w-4 h-4" />}
            label="DuckDB"
            status={health?.database === 'connected' ? 'online' : 'offline'}
          />
          <StatusRow
            icon={<Cloud className="w-4 h-4" />}
            label="Garmin Connect"
            status={syncStatus?.garmin_authenticated ? 'online' : syncLoading ? 'loading' : 'offline'}
          />
        </div>
      </Panel>

      <Panel variant="inset" title="GARMIN SYNC CENTER">
        {syncStatus?.garmin_authenticated ? (
          <div className="space-y-4">
            <div className="p-3 rounded border border-success-green/30">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-success-green font-mono flex items-center gap-2">
                    <CheckCircle className="w-4 h-4" />
                    {syncStatus.user_email ? `Authenticated as ${syncStatus.user_email}` : 'Authenticated'}
                  </div>
                  <div className="text-xs text-text-muted mt-1 font-mono">
                    Last sync: {syncStatus.last_sync || 'Never'}
                    {' | '}
                    Activities: {syncStatus.activities_synced}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => syncMutation.mutate({ max_activities: 50, download_fit: true })}
                    loading={syncMutation.isPending}
                  >
                    {syncMutation.isPending ? 'SYNCING...' : 'SYNC NOW'}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => logoutMutation.mutate()}
                    aria-label="Log out of Garmin"
                  >
                    <LogOut className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            </div>

            <SyncOptionsForm onSync={(options) => syncMutation.mutate(options)} isLoading={syncMutation.isPending} />

            <div className="p-3 rounded border border-neon-purple/30 flex items-center justify-between">
              <div>
                <div className="text-sm text-neon-purple font-mono">Health metrics (HRV, sleep, body battery)</div>
                <div className="text-xs text-text-muted mt-1 font-mono">
                  {healthStatus?.days_stored
                    ? `${healthStatus.days_stored} days stored, last ${healthStatus.last_date}`
                    : 'No health data yet'}
                </div>
              </div>
              <Button
                variant="purple"
                size="sm"
                onClick={() => healthSyncMutation.mutate()}
                loading={healthSyncMutation.isPending}
              >
                {healthSyncMutation.isPending ? 'SYNCING...' : 'SYNC LAST 7 DAYS'}
              </Button>
            </div>
          </div>
        ) : (
          <div className="p-4 rounded border border-text-muted/30 text-center">
            <XCircle className="w-6 h-6 text-danger-red mx-auto mb-2" />
            <div className="text-sm text-text-muted font-mono">NOT CONNECTED</div>
            <Button className="mt-3" onClick={() => setShowLoginModal(true)}>
              [CONNECT]
            </Button>
          </div>
        )}
      </Panel>

      <GarminLoginModal
        isOpen={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        onSuccess={() => {
          setShowLoginModal(false);
          setAlert({ type: 'success', message: 'GARMIN CONNECT AUTHENTICATED' });
          queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
        }}
      />
    </div>
  );
}
