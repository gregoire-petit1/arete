import { useState, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight, RefreshCw, Plus, X, Check } from 'lucide-react';
import {
  CalendarWeek,
  AdherenceBar,
  LoadingState,
  FlameIcon,
} from '@/components';
import { garminApi, type PlannedSessionCreate } from '@/lib/api';
import { cn } from '@/lib/utils';

// Session types per sport category
const CARDIO_SESSION_TYPES = [
  { value: 'recovery', label: 'Recovery', color: 'text-success-green' },
  { value: 'endurance', label: 'Endurance', color: 'text-neon-cyan' },
  { value: 'tempo', label: 'Tempo', color: 'text-warning-orange' },
  { value: 'intervals', label: 'Intervals', color: 'text-danger-red' },
  { value: 'long_run', label: 'Long Run', color: 'text-neon-purple' },
];

const STRENGTH_SESSION_TYPES = [
  { value: 'strength', label: 'Strength', color: 'text-neon-gold' },
  { value: 'hypertrophy', label: 'Hypertrophy', color: 'text-neon-cyan' },
  { value: 'power', label: 'Power', color: 'text-danger-red' },
  { value: 'deload', label: 'Deload', color: 'text-success-green' },
];

const OTHER_SESSION_TYPES = [
  { value: 'recovery', label: 'Recovery', color: 'text-success-green' },
  { value: 'endurance', label: 'Endurance', color: 'text-neon-cyan' },
  { value: 'other', label: 'Other', color: 'text-text-muted' },
];

const SPORTS = [
  { value: 'running', label: 'Running', category: 'cardio' },
  { value: 'cycling', label: 'Cycling', category: 'cardio' },
  { value: 'swimming', label: 'Swimming', category: 'cardio' },
  { value: 'strength', label: 'Strength', category: 'strength' },
  { value: 'other', label: 'Other', category: 'other' },
];

// Helper to get session types for a sport
const getSessionTypesForSport = (sport: string) => {
  const sportConfig = SPORTS.find(s => s.value === sport);
  if (!sportConfig) return OTHER_SESSION_TYPES;
  
  switch (sportConfig.category) {
    case 'cardio': return CARDIO_SESSION_TYPES;
    case 'strength': return STRENGTH_SESSION_TYPES;
    default: return OTHER_SESSION_TYPES;
  }
};

// Helper to get default session type for a sport
const getDefaultSessionType = (sport: string) => {
  const types = getSessionTypesForSport(sport);
  return types[0]?.value || 'endurance';
};

export function PlanningPage() {
  const queryClient = useQueryClient();
  const [weekOffset, setWeekOffset] = useState(0);
  const [showNewQuest, setShowNewQuest] = useState(false);

  // New Quest form state
  const [newQuest, setNewQuest] = useState<PlannedSessionCreate>({
    date: new Date().toISOString().split('T')[0],
    sport: 'running',
    session_type: 'endurance',
    target_duration_min: 45,
    description: '',
    source: 'manual',
  });

  // Get available session types based on selected sport
  const availableSessionTypes = useMemo(() => 
    getSessionTypesForSport(newQuest.sport || 'running'),
    [newQuest.sport]
  );

  // Update session type when sport changes (if current type is invalid)
  const handleSportChange = useCallback((sport: string) => {
    const validTypes = getSessionTypesForSport(sport);
    const currentTypeValid = validTypes.some(t => t.value === newQuest.session_type);
    
    setNewQuest(prev => ({
      ...prev,
      sport,
      // Reset to default type if current is not valid for new sport
      session_type: currentTypeValid ? prev.session_type : getDefaultSessionType(sport),
    }));
  }, [newQuest.session_type]);

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

  // Create Quest mutation
  const createQuestMutation = useMutation({
    mutationFn: garminApi.createPlanned,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['planned'] });
      queryClient.invalidateQueries({ queryKey: ['matchSummary'] });
      setShowNewQuest(false);
      setNewQuest({
        date: new Date().toISOString().split('T')[0],
        sport: 'running',
        session_type: 'endurance',
        target_duration_min: 45,
        description: '',
        source: 'manual',
      });
    },
  });


  // Filter sessions for current week (using merged sessions)
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
    <div className="min-h-screen bg-void px-4 py-4 sm:p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex justify-between items-center mb-4 sm:mb-8"
        >
          <h1 className="text-lg sm:text-2xl font-sans font-bold text-neon-cyan tracking-wider">
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
              onClick={() => setShowNewQuest(true)}
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 sm:px-4 sm:py-2 rounded',
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
          className="flex items-center justify-between mb-4 sm:mb-6"
        >
          <button
            onClick={() => setWeekOffset(prev => prev - 1)}
            className="p-2 text-text-muted hover:text-neon-cyan transition-colors"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <span className="font-mono text-xs sm:text-sm text-text-secondary">
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
          className="glass-panel p-3 sm:p-4 mb-4 sm:mb-8 overflow-x-auto"
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
          className="glass-panel p-3 sm:p-4 mb-4 sm:mb-8"
        >
          <h3 className="text-xs sm:text-sm font-mono text-text-muted mb-3 sm:mb-4 uppercase tracking-wider">
            ADHERENCE DASHBOARD
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-6">
            {/* Completion Rate */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-text-muted font-mono">Completion Rate</span>
                <span className="text-base sm:text-lg font-mono text-text-primary">
                  {Math.round((summary?.completion_rate || 0) * 100)}%
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
                <div className="text-xl sm:text-2xl font-mono font-bold text-warning-orange">
                  {streak}
                </div>
                <div className="text-xs text-text-muted font-mono">sessions matched</div>
              </div>
            </div>
          </div>

          {/* Stats row */}
          <div className="mt-4 pt-4 border-t border-text-muted/10 flex gap-4 sm:gap-6 text-xs font-mono">
            <span className="text-text-muted">
              Unmatched: <span className="text-warning-orange">{summary?.unmatched_actual || 0}</span>
            </span>
            <span className="text-text-muted">
              Skipped: <span className="text-danger-red">{summary?.unmatched_planned || 0}</span>
            </span>
          </div>
        </motion.div>

      </div>

      {/* New Quest Modal */}
      <AnimatePresence>
        {showNewQuest && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-void/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setShowNewQuest(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="glass-panel p-4 sm:p-6 max-w-md w-full"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4 sm:mb-6">
                <div className="flex items-center gap-2">
                  <Plus className="w-5 h-5 text-neon-cyan" />
                  <h3 className="text-lg font-sans text-neon-cyan">NEW QUEST</h3>
                </div>
                <button 
                  onClick={() => setShowNewQuest(false)}
                  className="p-1 hover:bg-text-muted/20 rounded transition-colors"
                >
                  <X className="w-5 h-5 text-text-muted" />
                </button>
              </div>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  createQuestMutation.mutate(newQuest);
                }}
                className="space-y-4"
              >
                {/* Date */}
                <div>
                  <label className="text-xs font-mono text-text-muted uppercase block mb-2">
                    Date
                  </label>
                  <input
                    type="date"
                    value={newQuest.date}
                    onChange={(e) => setNewQuest(prev => ({ ...prev, date: e.target.value }))}
                    className={cn(
                      'w-full bg-abyss border border-text-muted/30 rounded px-4 py-2',
                      'text-text-primary font-mono',
                      'focus:border-neon-cyan/50 outline-none transition-colors'
                    )}
                    required
                  />
                </div>

                {/* Sport */}
                <div>
                  <label className="text-xs font-mono text-text-muted uppercase block mb-2">
                    Sport
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {SPORTS.map((sport) => (
                      <button
                        key={sport.value}
                        type="button"
                        onClick={() => handleSportChange(sport.value)}
                        className={cn(
                          'px-3 py-1.5 rounded text-xs font-mono transition-all',
                          newQuest.sport === sport.value
                            ? 'bg-neon-cyan/20 border border-neon-cyan/50 text-neon-cyan'
                            : 'bg-abyss border border-text-muted/30 text-text-muted hover:border-text-muted/50'
                        )}
                      >
                        {sport.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Session Type */}
                <div>
                  <label className="text-xs font-mono text-text-muted uppercase block mb-2">
                    Type
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {availableSessionTypes.map((type) => (
                      <button
                        key={type.value}
                        type="button"
                        onClick={() => setNewQuest(prev => ({ ...prev, session_type: type.value }))}
                        className={cn(
                          'px-3 py-1.5 rounded text-xs font-mono transition-all',
                          newQuest.session_type === type.value
                            ? `bg-abyss border border-current ${type.color}`
                            : 'bg-abyss border border-text-muted/30 text-text-muted hover:border-text-muted/50'
                        )}
                      >
                        {type.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Duration */}
                <div>
                  <label className="text-xs font-mono text-text-muted uppercase block mb-2">
                    Target Duration (min)
                  </label>
                  <input
                    type="number"
                    value={newQuest.target_duration_min || ''}
                    onChange={(e) => setNewQuest(prev => ({ ...prev, target_duration_min: parseInt(e.target.value) || undefined }))}
                    placeholder="45"
                    min={1}
                    max={480}
                    className={cn(
                      'w-full bg-abyss border border-text-muted/30 rounded px-4 py-2',
                      'text-text-primary font-mono',
                      'focus:border-neon-cyan/50 outline-none transition-colors'
                    )}
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="text-xs font-mono text-text-muted uppercase block mb-2">
                    Description
                  </label>
                  <textarea
                    value={newQuest.description || ''}
                    onChange={(e) => setNewQuest(prev => ({ ...prev, description: e.target.value }))}
                    placeholder="Easy Z2 run, focus on form..."
                    rows={2}
                    className={cn(
                      'w-full bg-abyss border border-text-muted/30 rounded px-4 py-2',
                      'text-text-primary font-mono text-sm resize-none',
                      'focus:border-neon-cyan/50 outline-none transition-colors'
                    )}
                  />
                </div>

                {/* Submit */}
                <button
                  type="submit"
                  disabled={createQuestMutation.isPending}
                  className={cn(
                    'w-full flex items-center justify-center gap-2 px-4 py-3 rounded',
                    'bg-neon-cyan/20 border border-neon-cyan/50',
                    'text-neon-cyan font-mono text-sm',
                    'hover:bg-neon-cyan/30 transition-all',
                    'disabled:opacity-50 disabled:cursor-not-allowed'
                  )}
                >
                  {createQuestMutation.isPending ? (
                    <>
                      <div className="w-4 h-4 border-2 border-neon-cyan border-t-transparent rounded-full animate-spin" />
                      CREATING...
                    </>
                  ) : (
                    <>
                      <Check className="w-4 h-4" />
                      CREATE QUEST
                    </>
                  )}
                </button>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
