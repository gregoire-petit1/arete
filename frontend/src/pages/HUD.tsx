import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { PlannedSessionCard, isPlannedDone } from '@/components/PlannedSessionCard';
import { ArrowRight, Bot, Calendar, Dumbbell, Zap } from 'lucide-react';
import { ErrorState, LoadingState, MetricCard } from '@/components';
import { Panel } from '@/components/ui';
import { garminApi, garminHealthApi, metricsApi, settingsApi, tipsApi } from '@/lib/api';
import { cn, getZoneColor } from '@/lib/utils';
import { toLocalISODate } from '@/lib/dates';

/** Readiness / stress traffic lights as Tailwind classes (theme colors). */
const readinessTone = (score: number) =>
  score >= 70
    ? 'text-neon-cyan border-neon-cyan'
    : score >= 45
      ? 'text-neon-gold border-neon-gold'
      : 'text-danger-red border-danger-red';
const stressTone = (avg: number) => (avg > 40 ? 'text-danger-red' : avg > 25 ? 'text-neon-gold' : 'text-success-green');

const TIP_BORDER: Record<string, string> = {
  alert: 'border-danger-red',
  warning: 'border-warning-orange',
  info: 'border-neon-cyan',
};

function SectionHeader({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      {icon}
      <h2 className="text-sm font-mono text-text-muted uppercase tracking-wider">{title}</h2>
    </div>
  );
}

export function DashboardPage() {
  const today = toLocalISODate();

  const { data: userSettings } = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get });

  const { data: allPlanned, isLoading: plannedLoading } = useQuery({
    queryKey: ['planned', today, today],
    queryFn: () => garminApi.getPlanned(today, today),
  });
  const { data: todayActual } = useQuery({
    queryKey: ['actual'],
    queryFn: () => garminApi.getActual(),
    select: (data) => data.filter((s) => s.date.slice(0, 10) === today),
  });

  const {
    data: playerStats,
    isLoading: statsLoading,
    error: statsError,
    refetch: refetchStats,
  } = useQuery({
    queryKey: ['player-stats'],
    queryFn: metricsApi.getPlayerStats,
    refetchInterval: 60000,
  });

  const { data: fitness } = useQuery({
    queryKey: ['fitness'],
    queryFn: metricsApi.getFitness,
    refetchInterval: 60000,
  });

  const { data: workload } = useQuery({ queryKey: ['workload'], queryFn: metricsApi.getWorkload });

  const { data: healthData } = useQuery({
    queryKey: ['health-daily', today],
    queryFn: () => garminHealthApi.getDaily(today),
    refetchInterval: 60000,
    retry: false,
  });

  const { data: tip } = useQuery({
    queryKey: ['tip-daily'],
    queryFn: tipsApi.getDaily,
    staleTime: 1000 * 60 * 30,
  });

  if (plannedLoading || statsLoading) {
    return <LoadingState message="LOADING DASHBOARD..." />;
  }

  if (statsError) {
    return <ErrorState message="FAILED TO LOAD PLAYER STATS" onRetry={() => refetchStats()} />;
  }

  return (
    <div className="min-h-screen bg-void px-4 py-4 sm:p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <header className="flex justify-between items-center animate-fade-down">
          <div>
            <h1 className="text-lg sm:text-2xl font-sans font-bold text-text-primary tracking-wider">
              Hello, <span className="text-neon-cyan">{userSettings?.display_name || 'HUNTER'}</span>
            </h1>
            <p className="text-xs font-mono text-text-muted mt-0.5">
              {new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}
            </p>
          </div>
          {playerStats && (
            <div className="w-12 h-12 flex items-center justify-center rounded-full bg-abyss border-2 border-neon-gold font-mono text-neon-gold text-lg font-bold shadow-[0_0_12px_rgba(255,215,0,0.3)] transition-transform hover:scale-105">
              {playerStats.level}
            </div>
          )}
        </header>

        {/* Block 1: Today's Plan */}
        <Panel className="p-4">
          <SectionHeader icon={<Calendar className="w-4 h-4 text-neon-purple" />} title="TODAY'S PLAN" />
          {allPlanned && allPlanned.length > 0 ? (
            <div className="space-y-2">
              {allPlanned.map((session) => (
                <PlannedSessionCard
                  key={session.id}
                  session={session}
                  done={isPlannedDone(session, todayActual ?? [])}
                />
              ))}
              <div className="flex justify-end gap-4 pt-1 text-xs font-mono">
                <Link to="/planning" className="text-neon-cyan hover:underline">
                  Semaine →
                </Link>
                <Link to="/log" className="text-neon-gold hover:text-neon-gold/80 transition-colors">
                  Log this session →
                </Link>
              </div>
            </div>
          ) : (
            <div className="text-center py-4">
              <p className="text-sm font-mono text-text-muted mb-2">Rest day — no sessions planned</p>
              <Link to="/planning" className="text-xs font-mono text-neon-cyan hover:underline">
                + Add a session
              </Link>
            </div>
          )}
        </Panel>

        {/* Block 2: Player Status */}
        <Panel className="p-4" delay={0.1}>
          <SectionHeader icon={<Dumbbell className="w-4 h-4 text-neon-gold" />} title="PLAYER STATUS" />

          {playerStats && (
            <div className="space-y-3 mb-4">
              {[
                { stat: playerStats.hp, color: 'bg-danger-red', label: 'HP' },
                { stat: playerStats.mp, color: 'bg-neon-cyan', label: 'MP' },
                { stat: playerStats.xp, color: 'bg-neon-gold', label: 'XP' },
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

          <div className="grid grid-cols-3 gap-3">
            <MetricCard
              title="ACWR"
              value={workload?.acwr?.toFixed(2) ?? '—'}
              zone={workload?.acwr_zone ?? 'unknown'}
              zoneColor={getZoneColor(workload?.acwr_zone)}
            />
            <MetricCard
              title="TSB"
              value={fitness?.tsb ? `${fitness.tsb > 0 ? '+' : ''}${fitness.tsb.toFixed(1)}` : '—'}
              zone={fitness?.form_zone ?? 'unknown'}
              zoneColor={getZoneColor(fitness?.form_zone)}
            />
            <MetricCard
              title="TRAINING R."
              value={fitness?.readiness_score?.toFixed(0) ?? '—'}
              zone={fitness?.readiness_level ?? 'unknown'}
              zoneColor={getZoneColor(fitness?.readiness_level)}
            />
          </div>
        </Panel>

        {/* Block 3: Readiness */}
        {healthData && healthData.readiness_score != null && (
          <Panel className="p-4" delay={0.2}>
            <SectionHeader icon={<Zap className="w-4 h-4 text-neon-gold" />} title="READINESS" />

            <div className="flex items-center gap-6">
              <div
                className={cn(
                  'flex-shrink-0 w-20 h-20 rounded-full bg-abyss border-2 flex items-center justify-center',
                  readinessTone(healthData.readiness_score)
                )}
              >
                <span className="text-2xl font-mono font-bold">{healthData.readiness_score}</span>
              </div>

              <div className="flex-1 grid grid-cols-2 gap-x-6 gap-y-1.5">
                {healthData.hrv_last_night != null && (
                  <>
                    <span className="text-[10px] font-mono text-text-muted">HRV</span>
                    <span className="text-xs font-mono text-text-primary text-right">
                      {healthData.hrv_last_night} ms
                      {healthData.hrv_status && (
                        <span className="text-[10px] text-neon-cyan ml-1">
                          {healthData.hrv_status === 'BALANCED' ? '⚖' : healthData.hrv_status === 'LOW' ? '↓' : '↑'}
                        </span>
                      )}
                    </span>
                  </>
                )}
                {healthData.sleep_score != null && (
                  <>
                    <span className="text-[10px] font-mono text-text-muted">Sleep</span>
                    <span className="text-xs font-mono text-text-primary text-right">
                      {healthData.sleep_score}/100
                      {healthData.sleep_duration_sec != null && (
                        <span className="text-[10px] text-text-muted ml-1">
                          ({Math.round(healthData.sleep_duration_sec / 3600)}h
                          {Math.round((healthData.sleep_duration_sec % 3600) / 60)}min)
                        </span>
                      )}
                    </span>
                  </>
                )}
                {healthData.stress_avg != null && (
                  <>
                    <span className="text-[10px] font-mono text-text-muted">Stress</span>
                    <span className={cn('text-xs font-mono text-right', stressTone(healthData.stress_avg))}>
                      {healthData.stress_avg}
                    </span>
                  </>
                )}
                {healthData.steps != null && (
                  <>
                    <span className="text-[10px] font-mono text-text-muted">Steps</span>
                    <span className="text-xs font-mono text-text-primary text-right">
                      {healthData.steps.toLocaleString()}
                    </span>
                  </>
                )}
              </div>
            </div>
          </Panel>
        )}

        {/* Block 4: AI Tip */}
        {tip && (
          <section
            className={cn('glass-panel p-4 border-l-4 animate-scale-in', TIP_BORDER[tip.priority] ?? 'border-neon-cyan')}
          >
            <div className="flex items-start gap-3">
              <Bot className="w-5 h-5 text-text-muted mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-mono text-text-primary leading-relaxed">{tip.tip}</p>
                <span className="text-[10px] font-mono text-text-muted mt-2 inline-block opacity-60">AI-generated</span>
              </div>
            </div>
          </section>
        )}

        {/* Quick Actions Footer */}
        <div className="flex gap-3 animate-fade-in" style={{ animationDelay: '0.3s' }}>
          <Link
            to="/log"
            className="flex-1 flex items-center justify-center gap-2 glass-panel px-4 py-3 text-sm font-mono text-neon-cyan hover:bg-abyss/80 transition-colors"
          >
            <Dumbbell className="w-4 h-4" />
            Log Session
            <ArrowRight className="w-3 h-3" />
          </Link>
          <Link
            to="/planning"
            className="flex-1 flex items-center justify-center gap-2 glass-panel px-4 py-3 text-sm font-mono text-neon-purple hover:bg-abyss/80 transition-colors"
          >
            <Calendar className="w-4 h-4" />
            View Planning
            <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      </div>
    </div>
  );
}
