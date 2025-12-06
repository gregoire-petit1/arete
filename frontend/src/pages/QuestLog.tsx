import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight, RefreshCw, Plus, X, Wrench } from 'lucide-react';
import {
  CalendarWeek,
  AdherenceBar,
  FitDropzone,
  LoadingState,
  ErrorState,
  FlameIcon,
  getSportIconComponent,
  getSportColor,
} from '@/components';
import { garminApi } from '@/lib/api';
import { cn, formatDuration } from '@/lib/utils';
import type { ActualSession, PlannedSession } from '@/types';

export function QuestLogPage() {
  const queryClient = useQueryClient();
  const [weekOffset, setWeekOffset] = useState(0);
  const [showComingSoon, setShowComingSoon] = useState<string | null>(null);
  const [uploadResults, setUploadResults] = useState<Array<{
    filename: string;
    status: 'success' | 'error' | 'uploading';
    message?: string;
  }>>([]);

  // Calculate week start date (Monday)
  const getWeekStart = (offset: number) => {
    const today = new Date();
    const day = today.getDay();
    const diff = today.getDate() - day + (day === 0 ? -6 : 1) + offset * 7;
    const monday = new Date(today.setDate(diff));
    return monday.toISOString().split('T')[0];
  };

  const weekStart = getWeekStart(weekOffset);
  const weekEnd = (() => {
    const end = new Date(weekStart);
    end.setDate(end.getDate() + 6);
    return end.toISOString().split('T')[0];
  })();

  // Queries
  const { data: plannedSessions, isLoading: plannedLoading } = useQuery({
    queryKey: ['planned', weekStart, weekEnd],
    queryFn: () => garminApi.getPlanned(weekStart, weekEnd),
  });

  const { data: actualSessions, isLoading: actualLoading } = useQuery({
    queryKey: ['actual'],
    queryFn: () => garminApi.getActual(),
  });

  const { data: summary } = useQuery({
    queryKey: ['matchSummary'],
    queryFn: garminApi.getSummary,
  });

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      setUploadResults(prev => [
        { filename: file.name, status: 'uploading' },
        ...prev.slice(0, 4),
      ]);
      const result = await garminApi.uploadFit(file);
      return { file, result };
    },
    onSuccess: ({ file, result }) => {
      setUploadResults(prev =>
        prev.map(u =>
          u.filename === file.name
            ? {
                ...u,
                status: 'success' as const,
                message: `${result.sport || 'Activity'}, ${formatDuration(result.duration_seconds || 0)}`,
              }
            : u
        )
      );
      queryClient.invalidateQueries({ queryKey: ['actual'] });
      queryClient.invalidateQueries({ queryKey: ['matchSummary'] });
    },
    onError: (error, file) => {
      setUploadResults(prev =>
        prev.map(u =>
          u.filename === file.name
            ? { ...u, status: 'error' as const, message: String(error) }
            : u
        )
      );
    },
  });

  const handleUpload = useCallback(
    async (file: File) => {
      await uploadMutation.mutateAsync(file);
    },
    [uploadMutation]
  );

  // Filter sessions for current week
  const weekActual = actualSessions?.filter(s => {
    const date = s.date.split('T')[0];
    return date >= weekStart && date <= weekEnd;
  }) || [];

  if (plannedLoading || actualLoading) {
    return <LoadingState message="LOADING QUEST LOG..." />;
  }

  // Calculate streak (consecutive days with completed sessions)
  const streak = summary?.matched || 0;

  return (
    <div className="min-h-screen bg-void p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex justify-between items-center mb-8"
        >
          <h1 className="text-2xl font-display font-bold text-neon-cyan tracking-wider">
            QUEST LOG
          </h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => queryClient.invalidateQueries()}
              className={cn(
                'p-2 rounded transition-all duration-200',
                'text-text-muted hover:text-neon-cyan hover:bg-abyss'
              )}
            >
              <RefreshCw className="w-5 h-5" />
            </button>
            <button
              onClick={() => setShowComingSoon('Planifier une nouvelle session')}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded',
                'bg-neon-cyan/10 border border-neon-cyan/30',
                'text-neon-cyan font-mono text-sm',
                'hover:bg-neon-cyan/20 transition-all duration-200'
              )}
            >
              <Plus className="w-4 h-4" />
              NEW QUEST
            </button>
          </div>
        </motion.header>

        {/* Week Navigation */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center justify-between mb-6"
        >
          <button
            onClick={() => setWeekOffset(prev => prev - 1)}
            className="p-2 text-text-muted hover:text-neon-cyan transition-colors"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <span className="font-mono text-text-secondary">
            {new Date(weekStart).toLocaleDateString('fr-FR', {
              day: 'numeric',
              month: 'short',
            })}
            {' — '}
            {new Date(weekEnd).toLocaleDateString('fr-FR', {
              day: 'numeric',
              month: 'short',
              year: 'numeric',
            })}
          </span>
          <button
            onClick={() => setWeekOffset(prev => prev + 1)}
            disabled={weekOffset >= 0}
            className={cn(
              'p-2 transition-colors',
              weekOffset >= 0
                ? 'text-text-muted/30 cursor-not-allowed'
                : 'text-text-muted hover:text-neon-cyan'
            )}
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </motion.div>

        {/* Calendar Week */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel p-4 mb-8"
        >
          <CalendarWeek
            startDate={weekStart}
            plannedSessions={plannedSessions || []}
            actualSessions={weekActual}
          />
        </motion.div>

        {/* Adherence Dashboard */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-panel p-4 mb-8"
        >
          <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
            ADHERENCE DASHBOARD
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Completion Rate */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-text-muted font-mono">Completion Rate</span>
                <span className="text-lg font-mono text-text-primary">
                  {((summary?.completion_rate || 0) * 100).toFixed(0)}%
                </span>
              </div>
              <AdherenceBar score={(summary?.completion_rate || 0) * 100} size="lg" showLabel={false} />
            </div>

            {/* This Week */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-text-muted font-mono">This Week</span>
                <span className="text-sm font-mono text-text-secondary">
                  {summary?.matched || 0} / {summary?.total_planned || 0}
                </span>
              </div>
              <div className="flex gap-1">
                {Array.from({ length: summary?.total_planned || 0 }).map((_, i) => (
                  <div
                    key={i}
                    className={cn(
                      'w-4 h-4 rounded-sm',
                      i < (summary?.matched || 0)
                        ? 'bg-success-green'
                        : 'bg-text-muted/20'
                    )}
                  />
                ))}
              </div>
            </div>

            {/* Streak */}
            <div className="flex items-center gap-3">
              <div className="p-3 rounded-lg bg-warning-orange/10">
                <FlameIcon className="w-6 h-6 text-warning-orange" />
              </div>
              <div>
                <div className="text-2xl font-mono font-bold text-warning-orange">
                  {streak}
                </div>
                <div className="text-xs text-text-muted font-mono">days streak</div>
              </div>
            </div>
          </div>

          {/* Stats row */}
          <div className="mt-4 pt-4 border-t border-text-muted/10 flex gap-6 text-xs font-mono">
            <span className="text-text-muted">
              Unmatched: <span className="text-warning-orange">{summary?.unmatched_actual || 0}</span>
            </span>
            <span className="text-text-muted">
              Skipped: <span className="text-danger-red">{summary?.unmatched_planned || 0}</span>
            </span>
          </div>
        </motion.div>

        {/* Recent Quests */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-panel p-4 mb-8"
        >
          <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
            RECENT QUESTS
          </h3>
          <div className="space-y-3">
            {actualSessions?.slice(0, 5).map((session) => (
              <RecentQuestRow key={session.id} session={session} />
            ))}
            {(!actualSessions || actualSessions.length === 0) && (
              <div className="text-center py-6 text-text-muted font-mono text-sm">
                NO QUESTS COMPLETED YET
              </div>
            )}
          </div>
        </motion.div>

        {/* Upload Zone */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="glass-panel p-4"
        >
          <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
            UPLOAD ZONE
          </h3>
          <FitDropzone
            onUpload={handleUpload}
            isUploading={uploadMutation.isPending}
            recentUploads={uploadResults}
          />
        </motion.div>
      </div>

      {/* Coming Soon Modal */}
      <AnimatePresence>
        {showComingSoon && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-void/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setShowComingSoon(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="glass-panel p-6 max-w-md w-full"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Wrench className="w-5 h-5 text-warning-orange" />
                  <h3 className="text-lg font-display text-warning-orange">EN CONSTRUCTION</h3>
                </div>
                <button 
                  onClick={() => setShowComingSoon(null)}
                  className="p-1 hover:bg-text-muted/20 rounded transition-colors"
                >
                  <X className="w-5 h-5 text-text-muted" />
                </button>
              </div>
              <p className="text-sm font-mono text-text-muted mb-4">
                La fonctionnalité "<span className="text-neon-cyan">{showComingSoon}</span>" 
                est en cours de développement.
              </p>
              <div className="h-1 bg-shadow rounded overflow-hidden">
                <motion.div
                  className="h-full bg-warning-orange"
                  initial={{ width: '0%' }}
                  animate={{ width: '45%' }}
                  transition={{ duration: 1 }}
                />
              </div>
              <p className="text-[10px] font-mono text-text-muted mt-2">
                Progression: 45% │ ETA: v1.2.0
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function RecentQuestRow({ session }: { session: ActualSession }) {
  const SportIcon = getSportIconComponent(session.sport);
  const sportColor = getSportColor(session.sport);
  const isMatched = session.matched_planned_id !== null;
  
  return (
    <div
      className={cn(
        'flex items-center gap-4 p-3 rounded',
        'bg-abyss/50 border border-text-muted/10',
        'hover:border-neon-cyan/30 transition-all duration-200'
      )}
    >
      {/* Status indicator */}
      <div
        className={cn(
          'w-8 h-8 rounded flex items-center justify-center',
          isMatched
            ? 'bg-success-green/20 text-success-green'
            : 'bg-text-muted/20 text-text-muted'
        )}
      >
        {isMatched ? <span className="text-sm">✓</span> : <SportIcon size="sm" className={sportColor} />}
      </div>

      {/* Icon & Info */}
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <SportIcon size="sm" className={sportColor} />
          <span className="text-sm font-mono text-text-primary">
            {new Date(session.date).toLocaleDateString('fr-FR', {
              day: '2-digit',
              month: 'short',
            }).replace(' ', ' ')}
          </span>
          <span className="text-text-muted">—</span>
          <span className="text-sm font-mono text-text-secondary capitalize">
            {session.activity_type || session.sport}
          </span>
        </div>
        <div className="text-xs font-mono text-text-muted mt-1">
          {formatDuration(session.duration_seconds)}
          {session.distance_meters && (
            <> │ {(session.distance_meters / 1000).toFixed(2)} km</>
          )}
          {session.avg_hr && <> │ avg HR {session.avg_hr}</>}
        </div>
      </div>

      {/* Adherence */}
      {isMatched && (
        <div className="w-24">
          <AdherenceBar score={85} size="sm" />
        </div>
      )}

      {/* Unmatched label */}
      {!isMatched && (
        <span className="text-xs font-mono text-warning-orange">
          UNMATCHED
        </span>
      )}

      {/* Action */}
      <button className="text-xs font-mono text-neon-cyan hover:underline">
        [VIEW]
      </button>
    </div>
  );
}
