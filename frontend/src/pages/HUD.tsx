import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Heart, Zap, Star, Calendar, Dumbbell, Bot, ArrowRight } from 'lucide-react';
import {
  MetricCard,
  LoadingState,
  ErrorState,
} from '@/components';
import { getSportIconComponent } from '@/components/SportIcons';
import { metricsApi, garminApi, tipsApi } from '@/lib/api';
import { cn, getZoneColor } from '@/lib/utils';

function getTodayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

const stagger = {
  visible: { transition: { staggerChildren: 0.1 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

export function DashboardPage() {
  const today = getTodayISO();

  // Block 1: Today's planned sessions
  const { data: allPlanned, isLoading: plannedLoading } = useQuery({
    queryKey: ['planned', 'today'],
    queryFn: () => garminApi.getPlanned(),
    select: (data) => data.filter((s) => s.date === today),
  });

  // Block 2: Player stats
  const {
    data: playerStats,
    isLoading: statsLoading,
    error: statsError,
  } = useQuery({
    queryKey: ['player-stats'],
    queryFn: metricsApi.getPlayerStats,
    refetchInterval: 60000,
  });

  // Existing fitness/workload for metric cards
  const { data: fitness } = useQuery({
    queryKey: ['fitness'],
    queryFn: metricsApi.getFitness,
    refetchInterval: 60000,
  });

  const { data: workload } = useQuery({
    queryKey: ['workload'],
    queryFn: metricsApi.getWorkload,
  });

  // Block 3: AI Tip
  const { data: tip } = useQuery({
    queryKey: ['tip-daily'],
    queryFn: tipsApi.getDaily,
    staleTime: 1000 * 60 * 30,
  });

  if (plannedLoading || statsLoading) {
    return <LoadingState message="LOADING DASHBOARD..." />;
  }

  if (statsError) {
    return <ErrorState message="FAILED TO LOAD PLAYER STATS" />;
  }

  const tipBorderColor: Record<string, string> = {
    alert: 'border-danger-red',
    warning: 'border-warning-orange',
    info: 'border-neon-cyan',
  };

  return (
    <div className="min-h-screen bg-void px-4 py-4 sm:p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex justify-between items-center"
        >
          <h1 className="text-lg sm:text-2xl font-display font-bold text-neon-cyan tracking-wider">
            DASHBOARD
          </h1>
          {playerStats && (
            <motion.div
              whileHover={{ scale: 1.05 }}
              className="w-12 h-12 flex items-center justify-center rounded-full bg-abyss border-2 border-neon-gold font-mono text-neon-gold text-lg font-bold shadow-[0_0_12px_rgba(255,215,0,0.3)]"
            >
              {playerStats.level}
            </motion.div>
          )}
        </motion.header>

        {/* Block 1: Today's Plan */}
        <motion.section
          initial="hidden"
          animate="visible"
          variants={stagger}
          className="glass-panel p-4"
        >
          <motion.div variants={fadeUp}>
            <div className="flex items-center gap-2 mb-4">
              <Calendar className="w-4 h-4 text-neon-purple" />
              <h2 className="text-sm font-mono text-text-muted uppercase tracking-wider">
                TODAY&apos;S PLAN
              </h2>
            </div>

            {allPlanned && allPlanned.length > 0 ? (
              <div className="space-y-3">
                {allPlanned.map((session) => {
                  const IconComp = getSportIconComponent(session.sport);
                  return (
                    <div
                      key={session.id}
                      className="flex items-center justify-between bg-shadow/50 rounded-lg px-3 py-2"
                    >
                      <div className="flex items-center gap-3">
                        <IconComp className="w-5 h-5 text-neon-cyan" />
                        <div>
                          <span className="text-sm font-mono text-text-primary">
                            {session.description || session.session_type}
                          </span>
                          {session.duration_minutes && (
                            <span className="text-xs font-mono text-text-muted ml-2">
                              {session.duration_minutes} min
                            </span>
                          )}
                        </div>
                      </div>
                      <a
                        href="/log"
                        className="text-xs font-mono text-neon-gold hover:text-neon-gold/80 transition-colors"
                      >
                        Log this session →
                      </a>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-4">
                <p className="text-sm font-mono text-text-muted mb-2">
                  Rest day — no sessions planned
                </p>
                <a
                  href="/planning"
                  className="text-xs font-mono text-neon-cyan hover:underline"
                >
                  + Add a session
                </a>
              </div>
            )}
          </motion.div>
        </motion.section>

        {/* Block 2: Player Status */}
        <motion.section
          initial="hidden"
          animate="visible"
          variants={stagger}
          className="glass-panel p-4"
        >
          <motion.div variants={fadeUp}>
            <div className="flex items-center gap-2 mb-4">
              <Dumbbell className="w-4 h-4 text-neon-gold" />
              <h2 className="text-sm font-mono text-text-muted uppercase tracking-wider">
                PLAYER STATUS
              </h2>
            </div>

            {/* HP / MP / XP Bars */}
            {playerStats && (
              <div className="space-y-3 mb-4">
                {[
                  { stat: playerStats.hp, color: 'bg-danger-red', icon: Heart, label: 'HP' },
                  { stat: playerStats.mp, color: 'bg-neon-cyan', icon: Zap, label: 'MP' },
                  { stat: playerStats.xp, color: 'bg-neon-gold', icon: Star, label: 'XP' },
                ].map(({ stat, color, label }) => (
                  <div key={label} className="flex items-center gap-3">
                    <span className="text-xs font-mono text-text-muted w-8">{label}</span>
                    <div className="flex-1 h-3 bg-shadow rounded-full overflow-hidden">
                      <div
                        className={cn('h-full rounded-full transition-all duration-500', color)}
                        style={{ width: `${Math.min(100, (stat.current / stat.max) * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-text-secondary w-16 text-right">
                      {stat.current}/{stat.max}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Metric Cards */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <div className="grid grid-cols-3 gap-3 lg:col-span-2">
                <MetricCard
                  title="ACWR"
                  value={workload?.acwr?.toFixed(2) ?? '—'}
                  zone={workload?.acwr_zone ?? 'unknown'}
                  zoneColor={getZoneColor(workload?.acwr_zone)}
                />
                <MetricCard
                  title="TSB"
                  value={
                    fitness?.tsb
                      ? `${fitness.tsb > 0 ? '+' : ''}${fitness.tsb.toFixed(1)}`
                      : '—'
                  }
                  zone={fitness?.form_zone ?? 'unknown'}
                  zoneColor={getZoneColor(fitness?.form_zone)}
                />
                <MetricCard
                  title="READINESS"
                  value={`${fitness?.readiness_score?.toFixed(0) ?? 0}%`}
                  zone={fitness?.readiness_level ?? 'unknown'}
                  zoneColor={getZoneColor(fitness?.readiness_level)}
                />
              </div>
            </div>
          </motion.div>
        </motion.section>

        {/* Block 3: AI Tip */}
        {tip && (
          <motion.section
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className={cn(
              'glass-panel p-4 border-l-4',
              tipBorderColor[tip.priority] ?? 'border-neon-cyan'
            )}
          >
            <div className="flex items-start gap-3">
              <Bot className="w-5 h-5 text-text-muted mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-mono text-text-primary leading-relaxed">
                  {tip.tip}
                </p>
                <span className="text-[10px] font-mono text-text-muted mt-2 inline-block opacity-60">
                  AI-generated
                </span>
              </div>
            </div>
          </motion.section>
        )}

        {/* Quick Actions Footer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="flex gap-3"
        >
          <a
            href="/log"
            className="flex-1 flex items-center justify-center gap-2 glass-panel px-4 py-3 text-sm font-mono text-neon-cyan hover:bg-abyss/80 transition-colors"
          >
            <Dumbbell className="w-4 h-4" />
            Log Session
            <ArrowRight className="w-3 h-3" />
          </a>
          <a
            href="/planning"
            className="flex-1 flex items-center justify-center gap-2 glass-panel px-4 py-3 text-sm font-mono text-neon-purple hover:bg-abyss/80 transition-colors"
          >
            <Calendar className="w-4 h-4" />
            View Planning
            <ArrowRight className="w-3 h-3" />
          </a>
        </motion.div>
      </div>
    </div>
  );
}

// Keep backward compat
export { DashboardPage as HUDPage };
