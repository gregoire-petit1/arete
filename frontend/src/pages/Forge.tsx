import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Plus,
  TrendingUp,
  TrendingDown,
  Minus,
  X,
  Wrench,
} from 'lucide-react';
import { LoadingState, EmptyState, StrengthIcon } from '@/components';
import { AnatomicalHeatmap } from '@/components/AnatomicalHeatmap';
import { strengthApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { StrengthSession, Exercise } from '@/types';

export function ForgePage() {
  const [exerciseSearch, setExerciseSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [showComingSoon, setShowComingSoon] = useState<string | null>(null);

  // Queries
  const { data: volumeByMuscle, isLoading: volumeLoading } = useQuery({
    queryKey: ['volumeByMuscle'],
    queryFn: () => strengthApi.getVolumeByMuscle(),
  });

  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ['strengthSessions'],
    queryFn: () => strengthApi.getSessions(10),
  });

  const { data: exercises } = useQuery({
    queryKey: ['exercises', categoryFilter, exerciseSearch],
    queryFn: () =>
      strengthApi.getExercises({
        category: categoryFilter || undefined,
        search: exerciseSearch || undefined,
      }),
  });

  // Calculate weekly stats
  const weeklyVolume = sessions?.reduce((sum, s) => sum + (s.total_volume || 0), 0) || 0;
  const weeklySets = sessions?.reduce((sum, s) => sum + (s.total_sets || 0), 0) || 0;
  const avgRpe = sessions?.length
    ? sessions.reduce((sum, s) => sum + (s.overall_rpe || 0), 0) / sessions.length
    : 0;

  if (volumeLoading || sessionsLoading) {
    return <LoadingState message="INITIALIZING FORGE..." />;
  }

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
            THE FORGE
          </h1>
          <button
            onClick={() => setShowComingSoon('Créer une nouvelle session de musculation')}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded',
              'bg-neon-cyan/10 border border-neon-cyan/30',
              'text-neon-cyan font-mono text-sm',
              'hover:bg-neon-cyan/20 transition-all duration-200'
            )}
          >
            <Plus className="w-4 h-4" />
            NEW SESSION
          </button>
        </motion.header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column */}
          <div className="space-y-8">
            {/* Muscle Heatmap */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-panel p-4"
            >
              <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
                MUSCLE HEATMAP (7D VOLUME)
              </h3>
              <AnatomicalHeatmap volumeByMuscle={volumeByMuscle || {}} />
            </motion.div>

            {/* Weekly Volume Tracker */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="glass-panel p-4"
            >
              <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
                WEEKLY VOLUME TRACKER
              </h3>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="text-center">
                  <div className="text-2xl font-mono font-bold text-neon-cyan">
                    {(weeklyVolume / 1000).toFixed(1)}k
                  </div>
                  <div className="text-xs text-text-muted">Total Volume (kg)</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-mono font-bold text-neon-purple">
                    {weeklySets}
                  </div>
                  <div className="text-xs text-text-muted">Total Sets</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-mono font-bold text-warning-orange">
                    {avgRpe.toFixed(1)}
                  </div>
                  <div className="text-xs text-text-muted">Avg RPE</div>
                </div>
              </div>
              <div className="h-2 bg-shadow rounded overflow-hidden">
                <div
                  className="h-full bg-neon-cyan transition-all duration-500"
                  style={{ width: `${Math.min(100, (weeklyVolume / 20000) * 100)}%` }}
                />
              </div>
              <div className="text-xs text-text-muted mt-2 text-right">
                {((weeklyVolume / 20000) * 100).toFixed(0)}% of weekly target (20,000 kg)
              </div>
            </motion.div>
          </div>

          {/* Right Column */}
          <div className="space-y-8">
            {/* Personal Records */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="glass-panel p-4"
            >
              <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider flex items-center gap-2">
                <span className="text-neon-gold">◆</span>
                PERSONAL RECORDS [HALL OF FAME]
              </h3>
              <div className="grid grid-cols-3 gap-4">
                <PRCard
                  exercise="SQUAT"
                  weight={140}
                  estimated1RM={140}
                  trend="up"
                  trendValue={5}
                  date="28 Nov"
                />
                <PRCard
                  exercise="BENCH"
                  weight={100}
                  estimated1RM={100}
                  trend="up"
                  trendValue={2.5}
                  date="01 Dec"
                />
                <PRCard
                  exercise="DEADLIFT"
                  weight={180}
                  estimated1RM={180}
                  trend="plateau"
                  trendValue={0}
                  date="15 Nov"
                />
              </div>
            </motion.div>

            {/* Recent Sessions */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="glass-panel p-4"
            >
              <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
                RECENT SESSIONS
              </h3>
              <div className="space-y-3">
                {sessions?.slice(0, 5).map((session) => (
                  <SessionRow key={session.id} session={session} />
                ))}
                {(!sessions || sessions.length === 0) && (
                  <EmptyState message="NO SESSIONS YET" action="Start forging your strength" />
                )}
              </div>
            </motion.div>
          </div>
        </div>

        {/* Exercise Library */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="glass-panel p-4 mt-8"
        >
          <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
            EXERCISE LIBRARY
          </h3>

          {/* Search & Filters */}
          <div className="flex flex-wrap gap-3 mb-4">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="text"
                value={exerciseSearch}
                onChange={(e) => setExerciseSearch(e.target.value)}
                placeholder="Search exercises..."
                className="w-full bg-shadow border border-text-muted/30 rounded pl-10 pr-3 py-2 text-text-primary font-mono text-sm placeholder:text-text-muted"
              />
            </div>
            <div className="flex gap-1">
              {['compound', 'isolation', 'cardio', 'mobility'].map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(categoryFilter === cat ? null : cat)}
                  className={cn(
                    'px-3 py-1.5 rounded text-xs font-mono uppercase transition-all',
                    categoryFilter === cat
                      ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30'
                      : 'bg-abyss text-text-muted border border-text-muted/20 hover:text-text-secondary'
                  )}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Exercise Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-2">
            {exercises?.slice(0, 10).map((exercise) => (
              <div
                key={exercise.id}
                className={cn(
                  'p-3 rounded bg-abyss/50 border border-text-muted/10',
                  'hover:border-neon-cyan/30 transition-all cursor-pointer'
                )}
              >
                <div className="text-sm text-text-primary truncate">{exercise.name}</div>
                <div className="text-xs text-text-muted capitalize">{exercise.muscle_primary}</div>
              </div>
            ))}
          </div>

          <button 
            onClick={() => setShowComingSoon('Ajouter un exercice personnalisé')}
            className="mt-4 text-xs font-mono text-neon-cyan hover:underline"
          >
            [+ ADD CUSTOM EXERCISE]
          </button>
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
                  animate={{ width: '60%' }}
                  transition={{ duration: 1 }}
                />
              </div>
              <p className="text-[10px] font-mono text-text-muted mt-2">
                Progression: 60% │ ETA: v1.2.0
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function PRCard({
  exercise,
  weight,
  estimated1RM,
  trend,
  trendValue,
  date,
}: {
  exercise: string;
  weight: number;
  estimated1RM: number;
  trend: 'up' | 'down' | 'plateau';
  trendValue: number;
  date: string;
}) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;

  return (
    <div className="p-3 bg-abyss rounded border border-neon-gold/30 text-center">
      <div className="text-xs text-text-muted font-mono mb-1 uppercase tracking-wider">[{exercise}]</div>
      <div className="text-2xl font-mono font-bold text-neon-gold">{weight} kg</div>
      <div className="text-xs text-text-muted">Est 1RM</div>
      <div
        className={cn(
          'flex items-center justify-center gap-1 mt-2 text-xs font-mono',
          trend === 'up' && 'text-success-green',
          trend === 'down' && 'text-danger-red',
          trend === 'plateau' && 'text-text-muted'
        )}
      >
        <TrendIcon className="w-3 h-3" />
        {trend === 'up' && `+${trendValue}kg`}
        {trend === 'down' && `-${trendValue}kg`}
        {trend === 'plateau' && 'Plateau'}
      </div>
      <div className="text-[10px] text-text-muted mt-1">{date}</div>
    </div>
  );
}

function SessionRow({ session }: { session: StrengthSession }) {
  return (
    <div
      className={cn(
        'flex items-center gap-4 p-3 rounded',
        'bg-abyss/50 border border-text-muted/10',
        'hover:border-neon-cyan/30 transition-all cursor-pointer'
      )}
    >
      <StrengthIcon size="md" className="text-warning-orange" />
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-mono text-text-primary">
            {new Date(session.date).toLocaleDateString('fr-FR', {
              day: '2-digit',
              month: 'short',
            })}
          </span>
          <span className="text-text-muted">—</span>
          <span className="text-sm font-mono text-text-secondary">
            {session.name || 'Session'}
          </span>
        </div>
        <div className="text-xs font-mono text-text-muted mt-1">
          {session.duration_minutes && `${session.duration_minutes}min`}
          {' │ '}
          Volume: {(session.total_volume / 1000).toFixed(1)}k kg
          {' │ '}
          {session.total_sets} sets
        </div>
      </div>
      {session.overall_rpe && (
        <div
          className={cn(
            'px-2 py-0.5 rounded text-xs font-mono',
            session.overall_rpe <= 6 && 'bg-success-green/20 text-success-green',
            session.overall_rpe > 6 && session.overall_rpe <= 8 && 'bg-warning-orange/20 text-warning-orange',
            session.overall_rpe > 8 && 'bg-danger-red/20 text-danger-red'
          )}
        >
          RPE {session.overall_rpe}
        </div>
      )}
      <button className="text-xs font-mono text-neon-cyan hover:underline">
        [VIEW]
      </button>
    </div>
  );
}
