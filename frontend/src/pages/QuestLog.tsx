import { useCallback, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, Plus, RefreshCw } from 'lucide-react';
import { AdherenceBar, CalendarWeek, ErrorState, FlameIcon, LoadingState } from '@/components';
import { Button, Field, Input, Modal, ModalHeader, Panel, Textarea } from '@/components/ui';
import { garminApi, type PlannedSessionCreate } from '@/lib/api';
import { WeekPlanList } from './planning/WeekPlanList';
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

const getSessionTypesForSport = (sport: string) => {
  const sportConfig = SPORTS.find((s) => s.value === sport);
  switch (sportConfig?.category) {
    case 'cardio':
      return CARDIO_SESSION_TYPES;
    case 'strength':
      return STRENGTH_SESSION_TYPES;
    default:
      return OTHER_SESSION_TYPES;
  }
};

const getDefaultSessionType = (sport: string) => getSessionTypesForSport(sport)[0]?.value || 'endurance';

const emptyQuest = (): PlannedSessionCreate => ({
  date: new Date().toISOString().split('T')[0],
  sport: 'running',
  session_type: 'endurance',
  target_duration_min: 45,
  description: '',
  source: 'manual',
});

// Monday of the week `offset` weeks from now, ISO date
const getWeekStart = (offset: number) => {
  const today = new Date();
  const day = today.getDay();
  const diff = today.getDate() - day + (day === 0 ? -6 : 1) + offset * 7;
  return new Date(today.setDate(diff)).toISOString().split('T')[0];
};

const CHIP = 'px-3 py-1.5 rounded text-xs font-mono transition-all border';
const CHIP_IDLE = 'bg-abyss border-text-muted/30 text-text-muted hover:border-text-muted/50';

export function PlanningPage() {
  const queryClient = useQueryClient();
  const [weekOffset, setWeekOffset] = useState(0);
  const [showNewQuest, setShowNewQuest] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [newQuest, setNewQuest] = useState<PlannedSessionCreate>(emptyQuest);

  const availableSessionTypes = useMemo(
    () => getSessionTypesForSport(newQuest.sport || 'running'),
    [newQuest.sport]
  );

  const handleSportChange = useCallback(
    (sport: string) => {
      const validTypes = getSessionTypesForSport(sport);
      const currentTypeValid = validTypes.some((t) => t.value === newQuest.session_type);
      setNewQuest((prev) => ({
        ...prev,
        sport,
        session_type: currentTypeValid ? prev.session_type : getDefaultSessionType(sport),
      }));
    },
    [newQuest.session_type]
  );

  const weekStart = getWeekStart(weekOffset);
  const weekEnd = (() => {
    const end = new Date(weekStart);
    end.setDate(end.getDate() + 6);
    return end.toISOString().split('T')[0];
  })();

  const plannedQuery = useQuery({
    queryKey: ['planned', weekStart, weekEnd],
    queryFn: () => garminApi.getPlanned(weekStart, weekEnd),
  });

  const actualQuery = useQuery({
    queryKey: ['actual'],
    queryFn: () => garminApi.getActual(),
  });

  const { data: summary } = useQuery({
    queryKey: ['matchSummary', weekStart, weekEnd],
    queryFn: () => garminApi.getSummary(weekStart, weekEnd),
  });

  const createQuestMutation = useMutation({
    mutationFn: garminApi.createPlanned,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['planned'] });
      queryClient.invalidateQueries({ queryKey: ['matchSummary'] });
      setShowNewQuest(false);
      setNewQuest(emptyQuest());
    },
  });

  const weekActual =
    actualQuery.data?.filter((s) => {
      const date = s.date.split('T')[0];
      return date >= weekStart && date <= weekEnd;
    }) || [];

  if (plannedQuery.isLoading || actualQuery.isLoading) {
    return <LoadingState message="LOADING QUEST LOG..." />;
  }

  if (plannedQuery.isError || actualQuery.isError) {
    return (
      <ErrorState
        message="FAILED TO LOAD PLANNING"
        onRetry={() => {
          plannedQuery.refetch();
          actualQuery.refetch();
        }}
      />
    );
  }

  const completed = summary?.completed || 0;
  const due = summary?.planned_due || 0;

  return (
    <div className="min-h-screen bg-void px-4 py-4 sm:p-6">
      <div className="max-w-6xl mx-auto">
        <header className="flex justify-between items-center mb-4 sm:mb-8 animate-fade-down">
          <h1 className="text-lg sm:text-2xl font-sans font-bold text-neon-cyan tracking-wider">QUEST LOG</h1>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => queryClient.invalidateQueries()}
              className="p-2 rounded transition-all duration-200 text-text-muted hover:text-neon-cyan hover:bg-abyss"
              aria-label="Refresh"
            >
              <RefreshCw className="w-5 h-5" />
            </button>
            <Button onClick={() => setShowNewQuest(true)} className="px-3 py-1.5 sm:px-4 sm:py-2">
              <Plus className="w-4 h-4" />
              NEW QUEST
            </Button>
          </div>
        </header>

        {/* Week Navigation */}
        <div className="flex items-center justify-between mb-4 sm:mb-6 animate-fade-in">
          <button
            type="button"
            onClick={() => setWeekOffset((prev) => prev - 1)}
            className="p-2 text-text-muted hover:text-neon-cyan transition-colors"
            aria-label="Previous week"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <span className="font-mono text-xs sm:text-sm text-text-secondary">
            {new Date(weekStart).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
            {' — '}
            {new Date(weekEnd).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}
          </span>
          <button
            type="button"
            onClick={() => setWeekOffset((prev) => prev + 1)}
            disabled={weekOffset >= 0}
            className={cn(
              'p-2 transition-colors',
              weekOffset >= 0 ? 'text-text-muted/30 cursor-not-allowed' : 'text-text-muted hover:text-neon-cyan'
            )}
            aria-label="Next week"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>

        <Panel className="mb-4 sm:mb-8 overflow-x-auto">
          <CalendarWeek
            startDate={weekStart}
            plannedSessions={plannedQuery.data || []}
            actualSessions={weekActual}
            onDayClick={(d) => setSelectedDate((prev) => (prev === d ? null : d))}
          />
        </Panel>

        <Panel title="SÉANCES DE LA SEMAINE" className="mb-4 sm:mb-8" delay={0.05}>
          <WeekPlanList
            days={Array.from({ length: 7 }, (_, i) => {
              const d = new Date(weekStart);
              d.setDate(d.getDate() + i);
              return d.toISOString().split('T')[0];
            })}
            planned={plannedQuery.data || []}
            actual={weekActual}
            selectedDate={selectedDate}
            today={new Date().toISOString().split('T')[0]}
            onSelect={setSelectedDate}
          />
        </Panel>

        <Panel title="ADHERENCE DASHBOARD" className="mb-4 sm:mb-8" delay={0.1}>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-6">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-text-muted font-mono">Completion Rate</span>
                <span className="text-base sm:text-lg font-mono text-text-primary">
                  {Math.round(summary?.adherence_rate || 0)}%
                </span>
              </div>
              <AdherenceBar score={summary?.adherence_rate || 0} size="lg" showLabel={false} />
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-text-muted font-mono">Dues à ce jour</span>
                <span className="text-sm font-mono text-text-secondary">
                  {completed} / {due}
                </span>
              </div>
              <div className="flex gap-1 flex-wrap">
                {Array.from({ length: due }).map((_, i) => (
                  <div key={i} className={cn('w-4 h-4 rounded-sm', i < completed ? 'bg-success-green' : 'bg-text-muted/20')} />
                ))}
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="p-3 rounded-lg bg-warning-orange/10">
                <FlameIcon className="w-6 h-6 text-warning-orange" />
              </div>
              <div>
                <div className="text-xl sm:text-2xl font-mono font-bold text-warning-orange">{completed}</div>
                <div className="text-xs text-text-muted font-mono">séances faites</div>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-text-muted/10 flex gap-4 sm:gap-6 text-xs font-mono">
            <span className="text-text-muted">
              Hors plan: <span className="text-warning-orange">{summary?.total_unmatched || 0}</span>
            </span>
            <span className="text-text-muted">
              Manquées: <span className="text-danger-red">{summary?.skipped || 0}</span>
            </span>
          </div>
        </Panel>
      </div>

      <Modal open={showNewQuest} onClose={() => setShowNewQuest(false)} className="max-w-md p-4 sm:p-6">
        <ModalHeader
          title="NEW QUEST"
          icon={<Plus className="w-5 h-5" />}
          onClose={() => setShowNewQuest(false)}
          className="mb-4 sm:mb-6"
        />

        <form
          onSubmit={(e) => {
            e.preventDefault();
            createQuestMutation.mutate(newQuest);
          }}
          className="space-y-4"
        >
          <Field label="Date">
            <Input
              type="date"
              value={newQuest.date}
              onChange={(e) => setNewQuest((prev) => ({ ...prev, date: e.target.value }))}
              required
            />
          </Field>

          <Field label="Sport">
            <div className="flex flex-wrap gap-2">
              {SPORTS.map((sport) => (
                <button
                  key={sport.value}
                  type="button"
                  onClick={() => handleSportChange(sport.value)}
                  className={cn(
                    CHIP,
                    newQuest.sport === sport.value ? 'bg-neon-cyan/20 border-neon-cyan/50 text-neon-cyan' : CHIP_IDLE
                  )}
                >
                  {sport.label}
                </button>
              ))}
            </div>
          </Field>

          <Field label="Type">
            <div className="flex flex-wrap gap-2">
              {availableSessionTypes.map((type) => (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => setNewQuest((prev) => ({ ...prev, session_type: type.value }))}
                  className={cn(
                    CHIP,
                    newQuest.session_type === type.value ? `bg-abyss border-current ${type.color}` : CHIP_IDLE
                  )}
                >
                  {type.label}
                </button>
              ))}
            </div>
          </Field>

          <Field label="Target Duration (min)">
            <Input
              type="number"
              value={newQuest.target_duration_min || ''}
              onChange={(e) =>
                setNewQuest((prev) => ({ ...prev, target_duration_min: parseInt(e.target.value) || undefined }))
              }
              placeholder="45"
              min={1}
              max={480}
            />
          </Field>

          <Field label="Description">
            <Textarea
              value={newQuest.description || ''}
              onChange={(e) => setNewQuest((prev) => ({ ...prev, description: e.target.value }))}
              placeholder="Easy Z2 run, focus on form..."
              rows={2}
            />
          </Field>

          <Button type="submit" strong size="lg" fullWidth loading={createQuestMutation.isPending}>
            {createQuestMutation.isPending ? (
              'CREATING...'
            ) : (
              <>
                <Check className="w-4 h-4" />
                CREATE QUEST
              </>
            )}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
