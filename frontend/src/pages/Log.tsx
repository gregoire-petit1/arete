import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dumbbell, Heart, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AnatomicalHeatmap, EmptyState, ErrorState, LoadingState } from '@/components';
import { Button, Panel } from '@/components/ui';
import { strengthApi } from '@/lib/api';
import { CardioTab, LogSessionModal, SessionDetailModal, SessionRow, WeeklyVolumeTracker } from './log/index';
import { invalidateAfterSession } from '@/lib/queryKeys';

type Tab = 'force' | 'cardio';

const TABS: { id: Tab; label: string; icon: typeof Dumbbell }[] = [
  { id: 'force', label: 'FORCE', icon: Dumbbell },
  { id: 'cardio', label: 'CARDIO', icon: Heart },
];

export function LogPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>('force');
  const [showNewSession, setShowNewSession] = useState(false);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);

  const volumeQuery = useQuery({
    queryKey: ['volumeByMuscle'],
    queryFn: () => strengthApi.getVolumeByMuscle(),
  });

  const sessionsQuery = useQuery({
    queryKey: ['strengthSessions'],
    queryFn: () => strengthApi.getSessions(10),
  });

  const deleteSessionMutation = useMutation({
    mutationFn: (sessionId: number) => strengthApi.deleteSession(sessionId),
    onSuccess: () => {
      invalidateAfterSession(queryClient);
      setSelectedSessionId(null);
    },
  });

  if (volumeQuery.isLoading || sessionsQuery.isLoading) {
    return <LoadingState message="INITIALIZING LOG..." />;
  }

  if (sessionsQuery.isError) {
    return <ErrorState message="FAILED TO LOAD SESSIONS" onRetry={() => sessionsQuery.refetch()} />;
  }

  const sessions = sessionsQuery.data ?? [];

  return (
    <div className="min-h-screen bg-void px-4 py-4 sm:p-6">
      <div className="max-w-6xl mx-auto">
        <header className="flex justify-between items-center mb-4 sm:mb-8 animate-fade-down">
          <h1 className="text-lg sm:text-2xl font-sans font-bold text-neon-cyan tracking-wider">LOG</h1>
          {activeTab === 'force' && (
            <Button variant="gold" onClick={() => setShowNewSession(true)}>
              <Sparkles className="w-4 h-4" />
              LOG SESSION
            </Button>
          )}
        </header>

        <div className="flex gap-1 mb-6">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-t text-sm font-mono transition-all',
                activeTab === tab.id
                  ? 'bg-neon-gold/10 text-neon-gold border-b-2 border-neon-gold'
                  : 'text-text-muted hover:text-text-secondary'
              )}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'force' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-8">
            <div className="space-y-4 sm:space-y-8">
              <Panel title="MUSCLE HEATMAP (7D VOLUME)">
                {volumeQuery.isError ? (
                  <ErrorState message="VOLUME UNAVAILABLE" onRetry={() => volumeQuery.refetch()} />
                ) : (
                  <AnatomicalHeatmap volumeByMuscle={volumeQuery.data || {}} />
                )}
              </Panel>
              <WeeklyVolumeTracker sessions={sessions} />
            </div>

            <div className="space-y-4 sm:space-y-8">
              <Panel title="RECENT SESSIONS" delay={0.3}>
                <div className="space-y-3">
                  {sessions.slice(0, 5).map((session) => (
                    <SessionRow
                      key={session.id}
                      session={session}
                      onView={() => setSelectedSessionId(session.id)}
                      onDelete={() => deleteSessionMutation.mutate(session.id)}
                    />
                  ))}
                  {sessions.length === 0 && (
                    <EmptyState message="NO SESSIONS YET" action="Start logging your strength" />
                  )}
                </div>
              </Panel>
            </div>
          </div>
        )}

        {activeTab === 'cardio' && <CardioTab />}
      </div>

      <LogSessionModal open={showNewSession} onClose={() => setShowNewSession(false)} />
      <SessionDetailModal sessionId={selectedSessionId} onClose={() => setSelectedSessionId(null)} />
    </div>
  );
}
