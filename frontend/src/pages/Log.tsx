import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  X,
  Wrench,
  Check,
  Sparkles,
  AlertCircle,
  Link,
  Unlink,
  Dumbbell,
  Heart,
} from 'lucide-react';
import { LoadingState, EmptyState, StrengthIcon, FitDropzone } from '@/components';
import { AnatomicalHeatmap } from '@/components/AnatomicalHeatmap';
import { strengthApi, garminApi, tipsApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { StrengthSession } from '@/types';

// Parsed workout types
interface ParsedSet {
  set_number: number;
  reps: number | null;
  weight_kg: number | null;
  rpe: number | null;
  is_warmup: boolean;
  is_failure: boolean;
}

interface ParsedExercise {
  name: string;
  exercise_id: string | null;
  exercise_matched: boolean;
  sets: ParsedSet[];
  notes: string | null;
}

interface ParseResult {
  success: boolean;
  date: string;
  name: string | null;
  exercises: ParsedExercise[];
  duration_min: number | null;
  overall_rpe: number | null;
  notes: string | null;
  session_id: number | null;
  message: string | null;
}

export function LogPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'force' | 'cardio'>('force');
  const [showComingSoon, setShowComingSoon] = useState<string | null>(null);
  const [showNewSession, setShowNewSession] = useState(false);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);

  // Workout parsing state
  const [workoutText, setWorkoutText] = useState('');
  const [workoutDate, setWorkoutDate] = useState(new Date().toISOString().split('T')[0]);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [parseStep, setParseStep] = useState<'input' | 'preview' | 'saved'>('input');

  // Cardio state
  const [recentUploads, setRecentUploads] = useState<Array<{ filename: string; status: 'success' | 'error' | 'uploading'; message?: string }>>([]);
  const [feedback, setFeedback] = useState<{ feedback: string; highlights: string[] } | null>(null);

  // Queries
  const { data: volumeByMuscle, isLoading: volumeLoading } = useQuery({
    queryKey: ['volumeByMuscle'],
    queryFn: () => strengthApi.getVolumeByMuscle(),
  });

  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ['strengthSessions'],
    queryFn: () => strengthApi.getSessions(10),
  });

  // Query for selected session details
  const { data: selectedSession, isLoading: sessionDetailLoading } = useQuery({
    queryKey: ['strengthSession', selectedSessionId],
    queryFn: () => strengthApi.getSession(selectedSessionId!),
    enabled: selectedSessionId !== null,
  });

  // Parse workout mutation
  const parseWorkoutMutation = useMutation({
    mutationFn: ({ text, date, save }: { text: string; date: string; save: boolean }) =>
      strengthApi.parseWorkout(text, date, save),
    onSuccess: (data) => {
      setParseResult(data);
      if (data.session_id) {
        setParseStep('saved');
        queryClient.invalidateQueries({ queryKey: ['strengthSessions'] });
        queryClient.invalidateQueries({ queryKey: ['volumeByMuscle'] });
      } else {
        setParseStep('preview');
      }
    },
  });

  // Delete session mutation
  const deleteSessionMutation = useMutation({
    mutationFn: (sessionId: number) => strengthApi.deleteSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strengthSessions'] });
      queryClient.invalidateQueries({ queryKey: ['volumeByMuscle'] });
      setSelectedSessionId(null);
    },
  });

  // Query for Garmin candidates when viewing a session
  const { data: garminCandidates } = useQuery({
    queryKey: ['garminCandidates', selectedSessionId],
    queryFn: () => strengthApi.getGarminCandidates(selectedSessionId!),
    enabled: selectedSessionId !== null,
  });

  // Link to Garmin mutation
  const linkGarminMutation = useMutation({
    mutationFn: ({ sessionId, garminId }: { sessionId: number; garminId: number | null }) =>
      strengthApi.linkToGarmin(sessionId, garminId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strengthSession', selectedSessionId] });
      queryClient.invalidateQueries({ queryKey: ['garminCandidates', selectedSessionId] });
    },
  });

  // Cardio upload mutation
  const uploadMutation = useMutation({
    mutationFn: (file: File) => garminApi.uploadFit(file),
    onSuccess: async (result) => {
      setRecentUploads(prev => [{ filename: result.filename || 'activity.fit', status: 'success', message: 'Uploaded' }, ...prev]);
      queryClient.invalidateQueries({ queryKey: ['actual'] });
      // Try to get AI feedback if we have a session
      if (result.activity_id) {
        try {
          const tips = await tipsApi.getPostSession('cardio', result.activity_id);
          setFeedback(tips);
        } catch {
          // AI feedback is best-effort
        }
      }
    },
    onError: (error) => {
      setRecentUploads(prev => [{ filename: 'upload', status: 'error', message: String(error) }, ...prev]);
    },
  });

  const handleFitUpload = async (file: File) => {
    uploadMutation.mutate(file);
  };

  // Reset modal state
  const resetModal = () => {
    setShowNewSession(false);
    setWorkoutText('');
    setWorkoutDate(new Date().toISOString().split('T')[0]);
    setParseResult(null);
    setParseStep('input');
  };

  // Calculate weekly stats
  const weeklyVolume = sessions?.reduce((sum, s) => sum + (s.total_volume || 0), 0) || 0;
  const weeklySets = sessions?.reduce((sum, s) => sum + (s.total_sets || 0), 0) || 0;
  const avgRpe = sessions?.length
    ? sessions.reduce((sum, s) => sum + (s.overall_rpe || 0), 0) / sessions.length
    : 0;

  if (volumeLoading || sessionsLoading) {
    return <LoadingState message="INITIALIZING LOG..." />;
  }

  return (
    <div className="min-h-screen bg-void px-4 py-4 sm:p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex justify-between items-center mb-4 sm:mb-8"
        >
          <h1 className="text-lg sm:text-2xl font-display font-bold text-neon-cyan tracking-wider">
            LOG
          </h1>
          {activeTab === 'force' && (
            <button
              onClick={() => setShowNewSession(true)}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded',
                'bg-neon-gold/10 border border-neon-gold/30',
                'text-neon-gold font-mono text-sm',
                'hover:bg-neon-gold/20 transition-all duration-200'
              )}
            >
              <Sparkles className="w-4 h-4" />
              LOG SESSION
            </button>
          )}
        </motion.header>

        {/* Tab Bar */}
        <div className="flex gap-1 mb-6">
          <button
            onClick={() => setActiveTab('force')}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-t text-sm font-mono transition-all',
              activeTab === 'force'
                ? 'bg-neon-gold/10 text-neon-gold border-b-2 border-neon-gold'
                : 'text-text-muted hover:text-text-secondary'
            )}
          >
            <Dumbbell className="w-4 h-4" />
            FORCE
          </button>
          <button
            onClick={() => setActiveTab('cardio')}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-t text-sm font-mono transition-all',
              activeTab === 'cardio'
                ? 'bg-neon-gold/10 text-neon-gold border-b-2 border-neon-gold'
                : 'text-text-muted hover:text-text-secondary'
            )}
          >
            <Heart className="w-4 h-4" />
            CARDIO
          </button>
        </div>

        {/* Force Tab */}
        {activeTab === 'force' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-8">
            {/* Left Column */}
            <div className="space-y-4 sm:space-y-8">
              {/* Muscle Heatmap */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="glass-panel p-3 sm:p-4"
              >
                <h3 className="text-xs sm:text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
                  MUSCLE HEATMAP (7D VOLUME)
                </h3>
                <AnatomicalHeatmap volumeByMuscle={volumeByMuscle || {}} />
              </motion.div>

              {/* Weekly Volume Tracker */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="glass-panel p-3 sm:p-4"
              >
                <h3 className="text-xs sm:text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
                  WEEKLY VOLUME TRACKER
                </h3>
                <div className="grid grid-cols-3 gap-2 sm:gap-4 mb-4">
                  <div className="text-center">
                    <div className="text-lg sm:text-2xl font-mono font-bold text-neon-cyan">
                      {(weeklyVolume / 1000).toFixed(1)}k
                    </div>
                    <div className="text-xs text-text-muted font-mono">Total Volume (kg)</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg sm:text-2xl font-mono font-bold text-neon-purple">
                      {weeklySets}
                    </div>
                    <div className="text-[10px] sm:text-xs text-text-muted font-mono">Total Sets</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg sm:text-2xl font-mono font-bold text-warning-orange">
                      {avgRpe.toFixed(1)}
                    </div>
                    <div className="text-xs text-text-muted font-mono">Avg RPE</div>
                  </div>
                </div>
                <div className="h-2 bg-shadow rounded overflow-hidden">
                  <div
                    className="h-full bg-neon-cyan transition-all duration-500"
                    style={{ width: `${Math.min(100, (weeklyVolume / 20000) * 100)}%` }}
                  />
                </div>
                <div className="text-xs text-text-muted font-mono mt-2 text-right">
                  {((weeklyVolume / 20000) * 100).toFixed(0)}% of weekly target (20,000 kg)
                </div>
              </motion.div>
            </div>

            {/* Right Column */}
            <div className="space-y-4 sm:space-y-8">
              {/* Personal Records */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="glass-panel p-3 sm:p-4"
              >
                <h3 className="text-xs sm:text-sm font-mono text-text-muted mb-4 uppercase tracking-wider flex items-center gap-2">
                  <span className="text-neon-gold">◆</span>
                  PERSONAL RECORDS [HALL OF FAME]
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
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
                className="glass-panel p-3 sm:p-4"
              >
                <h3 className="text-xs sm:text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
                  RECENT SESSIONS
                </h3>
                <div className="space-y-3">
                  {sessions?.slice(0, 5).map((session) => (
                    <SessionRow
                      key={session.id}
                      session={session}
                      onView={() => setSelectedSessionId(session.id)}
                      onDelete={() => deleteSessionMutation.mutate(session.id)}
                    />
                  ))}
                  {(!sessions || sessions.length === 0) && (
                    <EmptyState message="NO SESSIONS YET" action="Start logging your strength" />
                  )}
                </div>
              </motion.div>
            </div>
          </div>
        )}

        {/* Cardio Tab */}
        {activeTab === 'cardio' && (
          <div className="space-y-4 sm:space-y-8">
            {/* Upload Zone */}
            <div className="glass-panel p-3 sm:p-4">
              <h3 className="text-xs sm:text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
                UPLOAD CARDIO SESSION
              </h3>
              <FitDropzone onUpload={handleFitUpload} isUploading={uploadMutation.isPending} recentUploads={recentUploads} />
            </div>

            {/* AI Feedback Card (shown after upload) */}
            {feedback && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="glass-panel p-3 sm:p-4"
              >
                <h3 className="text-xs sm:text-sm font-mono text-neon-cyan mb-3 uppercase tracking-wider flex items-center gap-2">
                  <Sparkles className="w-4 h-4" />
                  AI ANALYSIS
                </h3>
                <p className="text-sm font-mono text-text-secondary mb-3">{feedback.feedback}</p>
                {feedback.highlights.length > 0 && (
                  <ul className="space-y-1">
                    {feedback.highlights.map((h, i) => (
                      <li key={i} className="text-xs font-mono text-text-muted flex items-start gap-2">
                        <span className="text-neon-cyan mt-0.5">▸</span>
                        {h}
                      </li>
                    ))}
                  </ul>
                )}
              </motion.div>
            )}
          </div>
        )}
      </div>

      {/* Log Session Modal - Paste & Parse */}
      <AnimatePresence>
        {showNewSession && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-void/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={resetModal}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="glass-panel p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-neon-gold" />
                  <h3 className="text-lg font-display text-neon-gold">LOG SESSION</h3>
                </div>
                <button
                  onClick={resetModal}
                  className="p-1 hover:bg-text-muted/20 rounded transition-colors"
                >
                  <X className="w-5 h-5 text-text-muted" />
                </button>
              </div>

              {/* Step 1: Input */}
              {parseStep === 'input' && (
                <div className="space-y-4">
                  <p className="text-sm text-text-muted font-mono">
                    Colle ta séance ci-dessous. L'IA va parser automatiquement les exercices, sets et poids.
                  </p>

                  {/* Date */}
                  <div>
                    <label className="text-xs font-mono text-text-muted uppercase block mb-2">
                      Date
                    </label>
                    <input
                      type="date"
                      value={workoutDate}
                      onChange={(e) => setWorkoutDate(e.target.value)}
                      className={cn(
                        'w-full bg-abyss border border-text-muted/30 rounded px-4 py-2',
                        'text-text-primary font-mono',
                        'focus:border-neon-gold/50 outline-none transition-colors'
                      )}
                    />
                  </div>

                  {/* Workout Text */}
                  <div>
                    <label className="text-xs font-mono text-text-muted uppercase block mb-2">
                      Workout Log
                    </label>
                    <textarea
                      value={workoutText}
                      onChange={(e) => setWorkoutText(e.target.value)}
                      placeholder={`Bench press 4x8 80kg
Incline DB press 3x12 30kg
Cable flies 3x15
Triceps pushdown 4x12 RPE 8`}
                      rows={8}
                      className={cn(
                        'w-full bg-abyss border border-text-muted/30 rounded px-4 py-2',
                        'text-text-primary font-mono text-sm resize-none',
                        'focus:border-neon-gold/50 outline-none transition-colors',
                        'placeholder:text-text-muted/50'
                      )}
                    />
                  </div>

                  {/* Parse Button */}
                  <button
                    onClick={() => parseWorkoutMutation.mutate({
                      text: workoutText,
                      date: workoutDate,
                      save: false
                    })}
                    disabled={!workoutText.trim() || parseWorkoutMutation.isPending}
                    className={cn(
                      'w-full flex items-center justify-center gap-2 px-4 py-3 rounded',
                      'bg-neon-gold/20 border border-neon-gold/50',
                      'text-neon-gold font-mono text-sm',
                      'hover:bg-neon-gold/30 transition-all',
                      'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                  >
                    {parseWorkoutMutation.isPending ? (
                      <>
                        <div className="w-4 h-4 border-2 border-neon-gold border-t-transparent rounded-full animate-spin" />
                        PARSING...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        PARSE WORKOUT
                      </>
                    )}
                  </button>

                  {parseWorkoutMutation.isError && (
                    <div className="flex items-center gap-2 text-danger-red text-sm font-mono">
                      <AlertCircle className="w-4 h-4" />
                      {parseWorkoutMutation.error?.message || 'Parsing failed'}
                    </div>
                  )}
                </div>
              )}

              {/* Step 2: Preview */}
              {parseStep === 'preview' && parseResult && (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 text-success-green text-sm font-mono">
                    <Check className="w-4 h-4" />
                    {parseResult.exercises.length} exercice(s) détecté(s)
                  </div>

                  {/* Parsed Exercises */}
                  <div className="space-y-3 max-h-[40vh] overflow-y-auto">
                    {parseResult.exercises.map((ex, i) => (
                      <div
                        key={i}
                        className={cn(
                          'p-3 rounded border',
                          ex.exercise_matched
                            ? 'bg-abyss border-success-green/30'
                            : 'bg-abyss border-warning-orange/30'
                        )}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-mono text-sm text-text-primary">
                            {ex.name}
                          </span>
                          {ex.exercise_matched ? (
                            <span className="text-[10px] font-mono text-success-green">
                              ✓ MATCHED
                            </span>
                          ) : (
                            <span className="text-[10px] font-mono text-warning-orange">
                              ⚠ UNMATCHED
                            </span>
                          )}
                        </div>
                        <div className="text-xs font-mono text-text-muted">
                          {ex.sets.length} sets •
                          {ex.sets[0]?.weight_kg && ` ${ex.sets[0].weight_kg}kg`}
                          {ex.sets[0]?.is_failure
                            ? ' × failure'
                            : ex.sets[0]?.reps && ` × ${ex.sets[0].reps} reps`}
                          {ex.sets[0]?.rpe && ` @ RPE ${ex.sets[0].rpe}`}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Actions */}
                  <div className="flex gap-3">
                    <button
                      onClick={() => setParseStep('input')}
                      className={cn(
                        'flex-1 px-4 py-2 rounded',
                        'bg-abyss border border-text-muted/30',
                        'text-text-muted font-mono text-sm',
                        'hover:border-text-muted/50 transition-all'
                      )}
                    >
                      ← EDIT
                    </button>
                    <button
                      onClick={() => parseWorkoutMutation.mutate({
                        text: workoutText,
                        date: workoutDate,
                        save: true
                      })}
                      disabled={parseWorkoutMutation.isPending}
                      className={cn(
                        'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded',
                        'bg-neon-gold/20 border border-neon-gold/50',
                        'text-neon-gold font-mono text-sm',
                        'hover:bg-neon-gold/30 transition-all',
                        'disabled:opacity-50'
                      )}
                    >
                      {parseWorkoutMutation.isPending ? (
                        <div className="w-4 h-4 border-2 border-neon-gold border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <Check className="w-4 h-4" />
                      )}
                      SAVE
                    </button>
                  </div>
                </div>
              )}

              {/* Step 3: Saved */}
              {parseStep === 'saved' && parseResult && (
                <div className="space-y-4 text-center">
                  <div className="w-16 h-16 mx-auto rounded-full bg-success-green/20 flex items-center justify-center">
                    <Check className="w-8 h-8 text-success-green" />
                  </div>
                  <div>
                    <h4 className="font-display text-lg text-success-green">SESSION SAVED</h4>
                    <p className="text-sm font-mono text-text-muted mt-1">
                      {parseResult.message || `${parseResult.exercises.length} exercice(s) enregistré(s)`}
                    </p>
                  </div>
                  <button
                    onClick={resetModal}
                    className={cn(
                      'w-full px-4 py-3 rounded',
                      'bg-abyss border border-text-muted/30',
                      'text-text-primary font-mono text-sm',
                      'hover:border-neon-cyan/50 transition-all'
                    )}
                  >
                    CLOSE
                  </button>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

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

      {/* Session Detail Modal */}
      <AnimatePresence>
        {selectedSessionId !== null && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-abyss/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setSelectedSessionId(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass-panel p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-mono text-neon-gold uppercase tracking-wider">
                  SESSION DETAILS
                </h2>
                <button
                  onClick={() => setSelectedSessionId(null)}
                  className="p-2 hover:bg-white/5 rounded transition-colors"
                >
                  <X className="w-5 h-5 text-text-muted" />
                </button>
              </div>

              {sessionDetailLoading ? (
                <LoadingState />
              ) : selectedSession ? (
                <div className="space-y-6">
                  {/* Session Header */}
                  <div className="flex items-center justify-between border-b border-text-muted/20 pb-4">
                    <div>
                      <div className="text-sm font-mono text-text-muted">
                        {new Date(selectedSession.date).toLocaleDateString('fr-FR', {
                          weekday: 'long',
                          day: 'numeric',
                          month: 'long',
                          year: 'numeric',
                        })}
                      </div>
                      <div className="text-xl font-mono text-text-primary mt-1">
                        {selectedSession.name || 'Session'}
                      </div>
                    </div>
                    <div className="text-right">
                      {selectedSession.duration_min && (
                        <div className="text-sm font-mono text-text-muted">
                          {selectedSession.duration_min} min
                        </div>
                      )}
                      {selectedSession.overall_rpe && (
                        <div className={cn(
                          'text-sm font-mono mt-1',
                          selectedSession.overall_rpe <= 6 && 'text-success-green',
                          selectedSession.overall_rpe > 6 && selectedSession.overall_rpe <= 8 && 'text-warning-orange',
                          selectedSession.overall_rpe > 8 && 'text-danger-red'
                        )}>
                          RPE {selectedSession.overall_rpe}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="grid grid-cols-3 gap-2 sm:gap-4">
                    <div className="text-center p-2 sm:p-3 bg-abyss rounded border border-text-muted/20">
                      <div className="text-lg sm:text-2xl font-mono text-neon-cyan">
                        {selectedSession.exercises_count || selectedSession.exercises?.length || 0}
                      </div>
                      <div className="text-xs font-mono text-text-muted uppercase">Exercises</div>
                    </div>
                    <div className="text-center p-2 sm:p-3 bg-abyss rounded border border-text-muted/20">
                      <div className="text-lg sm:text-2xl font-mono text-neon-gold">
                        {selectedSession.total_sets || 0}
                      </div>
                      <div className="text-[10px] sm:text-xs font-mono text-text-muted uppercase">Sets</div>
                    </div>
                    <div className="text-center p-2 sm:p-3 bg-abyss rounded border border-text-muted/20">
                      <div className="text-lg sm:text-2xl font-mono text-success-green">
                        {((selectedSession.total_volume || 0) / 1000).toFixed(1)}k
                      </div>
                      <div className="text-xs font-mono text-text-muted uppercase">Volume (kg)</div>
                    </div>
                  </div>

                  {/* Exercises List */}
                  {selectedSession.exercises && selectedSession.exercises.length > 0 && (
                    <div>
                      <h3 className="text-sm font-mono text-text-muted uppercase tracking-wider mb-3">
                        Exercises
                      </h3>
                      <div className="space-y-3">
                        {selectedSession.exercises.map((ex, idx) => (
                          <div
                            key={idx}
                            className="p-3 bg-abyss rounded border border-text-muted/20"
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="font-mono text-text-primary">
                                {ex.exercise?.name || `Exercise #${ex.exercise_id}`}
                              </span>
                              <span className="text-xs font-mono text-text-muted">
                                {ex.sets?.length || 0} sets
                              </span>
                            </div>
                            {ex.sets && ex.sets.length > 0 && (
                              <div className="flex flex-wrap gap-2">
                                {ex.sets.map((set, setIdx) => (
                                  <div
                                    key={setIdx}
                                    className={cn(
                                      'px-2 py-1 rounded text-xs font-mono',
                                      set.is_warmup
                                        ? 'bg-info-blue/20 text-info-blue'
                                        : 'bg-neon-gold/10 text-neon-gold'
                                    )}
                                  >
                                    {set.weight_kg && `${set.weight_kg}kg × `}
                                    {set.reps !== null ? `${set.reps}` : 'failure'}
                                    {set.rpe && ` @${set.rpe}`}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Notes */}
                  {selectedSession.notes && (
                    <div>
                      <h3 className="text-sm font-mono text-text-muted uppercase tracking-wider mb-2">
                        Notes
                      </h3>
                      <p className="text-sm text-text-secondary font-mono">
                        {selectedSession.notes}
                      </p>
                    </div>
                  )}

                  {/* Garmin Link Section */}
                  <div className="border-t border-text-muted/20 pt-4">
                    <h3 className="text-sm font-mono text-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                      <Link className="w-4 h-4" />
                      Garmin Sync
                    </h3>

                    {selectedSession.garmin_activity_id ? (
                      <div className="flex items-center justify-between p-3 bg-success-green/10 rounded border border-success-green/30">
                        <div className="flex items-center gap-2">
                          <Check className="w-4 h-4 text-success-green" />
                          <span className="text-sm font-mono text-success-green">
                            Linked to Garmin #{selectedSession.garmin_activity_id}
                          </span>
                        </div>
                        <button
                          onClick={() => linkGarminMutation.mutate({
                            sessionId: selectedSessionId!,
                            garminId: null
                          })}
                          disabled={linkGarminMutation.isPending}
                          className="p-2 hover:bg-danger-red/20 rounded text-danger-red transition-colors"
                          title="Unlink"
                        >
                          <Unlink className="w-4 h-4" />
                        </button>
                      </div>
                    ) : garminCandidates?.candidates && garminCandidates.candidates.length > 0 ? (
                      <div className="space-y-2">
                        <p className="text-xs text-text-muted font-mono mb-2">
                          Found {garminCandidates.candidates.length} matching Garmin activity(s):
                        </p>
                        {garminCandidates.candidates.map((candidate) => (
                          <button
                            key={candidate.id}
                            onClick={() => linkGarminMutation.mutate({
                              sessionId: selectedSessionId!,
                              garminId: candidate.id
                            })}
                            disabled={linkGarminMutation.isPending}
                            className="w-full p-3 bg-abyss hover:bg-neon-cyan/10 rounded border border-text-muted/20 hover:border-neon-cyan/50 transition-colors text-left"
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <span className="text-sm font-mono text-text-primary">
                                  {candidate.date}
                                </span>
                                <span className="text-xs font-mono text-text-muted ml-2">
                                  ({Math.round(candidate.duration_seconds / 60)} min)
                                </span>
                              </div>
                              <span className="text-xs font-mono text-neon-cyan uppercase">
                                [LINK]
                              </span>
                            </div>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="p-3 bg-abyss rounded border border-text-muted/20">
                        <p className="text-sm font-mono text-text-muted text-center">
                          No matching Garmin activities found
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <EmptyState message="Session not found" />
              )}
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
  estimated1RM: _estimated1RM,
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
      <div className="text-lg sm:text-2xl font-mono font-bold text-neon-gold">{weight} kg</div>
      <div className="text-xs text-text-muted font-mono">Est 1RM</div>
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

function SessionRow({ session, onView, onDelete }: { session: StrengthSession; onView: () => void; onDelete: () => void }) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 sm:gap-4 p-2 sm:p-3 rounded',
        'bg-abyss/50 border border-text-muted/10',
        'hover:border-neon-cyan/30 transition-all cursor-pointer'
      )}
      onClick={onView}
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
        <div className="text-[10px] sm:text-xs font-mono text-text-muted mt-1">
          {session.duration_min && `${session.duration_min}min`}
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
      <button
        className="text-xs font-mono text-neon-cyan hover:underline"
        onClick={(e) => {
          e.stopPropagation();
          onView();
        }}
      >
        [VIEW]
      </button>
      <button
        className="text-xs font-mono text-danger-red hover:underline"
        onClick={(e) => {
          e.stopPropagation();
          if (confirm('Delete this session?')) {
            onDelete();
          }
        }}
      >
        [DEL]
      </button>
    </div>
  );
}
