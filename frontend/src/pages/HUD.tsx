import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Heart, Brain, Zap } from 'lucide-react';
import {
  StatusBar,
  MetricCard,
  SystemMessage,
  LoadChart,
  SessionTimeline,
  LoadingState,
  ErrorState,
} from '@/components';
import { metricsApi, logApi } from '@/lib/api';
import { getZoneColor, calculateLevel, normalizeTSB } from '@/lib/utils';

export function HUDPage() {
  // Fetch all data in parallel
  const { data: fitness, isLoading: fitnessLoading, error: fitnessError } = useQuery({
    queryKey: ['fitness'],
    queryFn: metricsApi.getFitness,
    refetchInterval: 60000,
  });

  const { data: workload, isLoading: workloadLoading } = useQuery({
    queryKey: ['workload'],
    queryFn: metricsApi.getWorkload,
  });

  const { data: recommendations } = useQuery({
    queryKey: ['recommendations'],
    queryFn: metricsApi.getRecommendations,
  });

  const { data: recentSessions } = useQuery({
    queryKey: ['recent'],
    queryFn: () => logApi.getRecent(5),
  });

  // Loading state
  if (fitnessLoading || workloadLoading) {
    return <LoadingState message="INITIALIZING HUD..." />;
  }

  // Error state
  if (fitnessError) {
    return <ErrorState message="FAILED TO LOAD METRICS" />;
  }

  // Calculate derived values
  const level = fitness ? calculateLevel(fitness.ctl) : 1;
  const mpValue = fitness ? normalizeTSB(fitness.tsb) : 50;
  const totalXP = 4500; // TODO: Calculate from session history

  // Transform session data for chart
  const chartData = recentSessions?.rows?.map((s) => ({
    date: s.date,
    load: s.tss || s.rpe ? (s.tss || 0) + (s.rpe || 0) * 10 : 50,
  })) || [];

  const topRecommendation = recommendations?.recommendations?.[0];

  return (
    <div className="min-h-screen bg-void px-4 py-4 sm:p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header with Level */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex justify-between items-center mb-6 sm:mb-8"
        >
          <h1 className="text-lg sm:text-2xl font-display font-bold text-neon-cyan tracking-wider">
            PLAYER STATUS
          </h1>
          <motion.div
            whileHover={{ scale: 1.05 }}
            className="px-4 py-2 bg-abyss border border-neon-gold rounded font-mono text-neon-gold shadow-[0_0_10px_rgba(255,215,0,0.3)]"
          >
            LVL {level}
          </motion.div>
        </motion.header>

        {/* Status Bars */}
        <motion.section
          initial="hidden"
          animate="visible"
          variants={{
            visible: { transition: { staggerChildren: 0.1 } },
          }}
          className="space-y-3 sm:space-y-4 mb-6 sm:mb-8"
        >
          <StatusBar
            label="HP"
            current={fitness?.readiness_score ?? 0}
            max={100}
            color="green"
            icon={<Heart className="w-4 h-4" />}
            subtitle="Recovery"
          />
          <StatusBar
            label="MP"
            current={mpValue}
            max={100}
            color="purple"
            icon={<Brain className="w-4 h-4" />}
            subtitle="Form"
          />
          <StatusBar
            label="XP"
            current={totalXP}
            max={10000}
            color="gold"
            icon={<Zap className="w-4 h-4" />}
            subtitle="→ Next Level"
          />
        </motion.section>

        {/* Metric Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 mb-6 sm:mb-8">
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

        {/* System Message */}
        {topRecommendation && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mb-6 sm:mb-8"
          >
            <SystemMessage
              content={topRecommendation.message}
              priority={topRecommendation.priority}
              actions={topRecommendation.actions}
            />
          </motion.div>
        )}

        {/* Load Chart */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel p-3 sm:p-4 mb-6 sm:mb-8"
        >
          <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
            CHARGE HEBDOMADAIRE
          </h3>
          <LoadChart
            data={chartData}
            acuteLoad={workload?.acute_load}
            chronicLoad={workload?.chronic_load}
          />
          <div className="flex justify-between mt-4 text-xs font-mono text-text-muted">
            <span>
              Acute:{' '}
              <span className="text-neon-cyan">
                {workload?.acute_load?.toFixed(0) ?? '—'}
              </span>
            </span>
            <span>
              Chronic:{' '}
              <span className="text-neon-purple">
                {workload?.chronic_load?.toFixed(0) ?? '—'}
              </span>
            </span>
          </div>
        </motion.div>

        {/* Recent Sessions */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-panel p-3 sm:p-4"
        >
          <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
            DERNIÈRES SESSIONS
          </h3>
          <SessionTimeline sessions={recentSessions?.rows ?? []} />
        </motion.div>
      </div>
    </div>
  );
}
