import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, AlertTriangle, Check, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button, Field, Input, Modal, ModalHeader, Textarea } from '@/components/ui';
import { strengthApi } from '@/lib/api';
import type { ParsedWorkout } from '@/types';
import { toLocalISODate } from '@/lib/dates';
import { invalidateAfterSession } from '@/lib/queryKeys';

const today = () => toLocalISODate();

interface LogSessionModalProps {
  open: boolean;
  onClose: () => void;
}

/** Paste → parse → preview → save flow for strength sessions. */
export function LogSessionModal({ open, onClose }: LogSessionModalProps) {
  const queryClient = useQueryClient();
  const [workoutText, setWorkoutText] = useState('');
  const [workoutDate, setWorkoutDate] = useState(today);
  const [parseResult, setParseResult] = useState<ParsedWorkout | null>(null);
  const [step, setStep] = useState<'input' | 'preview' | 'saved'>('input');

  const parseMutation = useMutation({
    mutationFn: ({ save }: { save: boolean }) => strengthApi.parseWorkout(workoutText, workoutDate, save),
    onSuccess: (data) => {
      setParseResult(data);
      if (data.session_id) {
        setStep('saved');
        invalidateAfterSession(queryClient);
      } else {
        setStep('preview');
      }
    },
  });

  const reset = () => {
    setWorkoutText('');
    setWorkoutDate(today());
    setParseResult(null);
    setStep('input');
    onClose();
  };

  const unparsed = parseResult?.unparsed_lines ?? [];

  return (
    <Modal open={open} onClose={reset} className="max-w-lg max-h-[90vh] overflow-y-auto">
      <ModalHeader
        title="SAISIR UNE SÉANCE"
        tone="text-neon-gold"
        icon={<Sparkles className="w-5 h-5" />}
        onClose={reset}
      />

      {step === 'input' && (
        <div className="space-y-4">
          <p className="text-sm text-text-muted font-mono">
            Colle ta séance ci-dessous. Les exercices, séries et charges sont extraits automatiquement.
          </p>

          <Field label="Date">
            <Input
              type="date"
              accent="gold"
              value={workoutDate}
              onChange={(e) => setWorkoutDate(e.target.value)}
            />
          </Field>

          <Field label="Séance en texte libre">
            <Textarea
              accent="gold"
              value={workoutText}
              onChange={(e) => setWorkoutText(e.target.value)}
              onKeyDown={(e) => {
                // Enter inserts a line; Ctrl/Cmd+Enter runs the parser
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && workoutText.trim()) {
                  e.preventDefault();
                  parseMutation.mutate({ save: false });
                }
              }}
              placeholder={`Bench press 4x8 80kg
4x10 @60 incline db press r2'
5x(10 pull ups, 15 dips) r1'30
(dips) 3x amrap`}
              rows={8}
            />
          </Field>

          <Button
            variant="gold"
            strong
            size="lg"
            fullWidth
            onClick={() => parseMutation.mutate({ save: false })}
            disabled={!workoutText.trim()}
            loading={parseMutation.isPending}
          >
            {parseMutation.isPending ? (
              'ANALYSE…'
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                PARSE WORKOUT
              </>
            )}
          </Button>

          {parseMutation.isError && (
            <div className="flex items-center gap-2 text-danger-red text-sm font-mono">
              <AlertCircle className="w-4 h-4" />
              {parseMutation.error?.message || 'Parsing failed'}
            </div>
          )}
        </div>
      )}

      {step === 'preview' && parseResult && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-success-green text-sm font-mono">
            <Check className="w-4 h-4" />
            {parseResult.exercises.length} exercice(s) détecté(s)
          </div>

          <div className="space-y-3 max-h-[40vh] overflow-y-auto">
            {parseResult.exercises.map((ex, i) => (
              <div
                key={i}
                className={cn(
                  'p-3 rounded border bg-abyss',
                  ex.exercise_matched ? 'border-success-green/30' : 'border-warning-orange/30'
                )}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-sm text-text-primary">{ex.name}</span>
                  {ex.exercise_matched ? (
                    <span className="text-[10px] font-mono text-success-green">✓ MATCHED</span>
                  ) : (
                    <span className="text-[10px] font-mono text-warning-orange">⚠ UNMATCHED</span>
                  )}
                </div>
                <div className="text-xs font-mono text-text-muted">
                  {ex.sets.length} sets •
                  {ex.sets[0]?.weight_kg && ` ${ex.sets[0].weight_kg}kg`}
                  {ex.sets[0]?.is_failure ? ' × failure' : ex.sets[0]?.reps && ` × ${ex.sets[0].reps} reps`}
                  {ex.sets[0]?.rpe && ` @ RPE ${ex.sets[0].rpe}`}
                </div>
              </div>
            ))}
          </div>

          {unparsed.length > 0 && (
            <div className="p-3 rounded border border-warning-orange/30 bg-warning-orange/5">
              <div className="flex items-center gap-2 text-warning-orange text-xs font-mono uppercase tracking-wider mb-2">
                <AlertTriangle className="w-4 h-4" />
                Lignes non reconnues ({unparsed.length})
              </div>
              <ul className="space-y-1">
                {unparsed.map((line, i) => (
                  <li key={i} className="text-xs font-mono text-text-secondary truncate">
                    › {line}
                  </li>
                ))}
              </ul>
              <p className="text-[10px] font-mono text-text-muted mt-2">
                Ces lignes ne seront pas enregistrées. Corrige le texte ou vérifie la notation.
              </p>
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="outline" className="flex-1" onClick={() => setStep('input')}>
              ← EDIT
            </Button>
            <Button
              variant="gold"
              strong
              className="flex-1"
              onClick={() => parseMutation.mutate({ save: true })}
              loading={parseMutation.isPending}
            >
              {!parseMutation.isPending && <Check className="w-4 h-4" />}
              SAVE
            </Button>
          </div>
        </div>
      )}

      {step === 'saved' && parseResult && (
        <div className="space-y-4 text-center">
          <div className="w-16 h-16 mx-auto rounded-full bg-success-green/20 flex items-center justify-center">
            <Check className="w-8 h-8 text-success-green" />
          </div>
          <div>
            <h4 className="font-sans text-lg text-success-green">SÉANCE ENREGISTRÉE</h4>
            <p className="text-sm font-mono text-text-muted mt-1">
              {parseResult.message || `${parseResult.exercises.length} exercice(s) enregistré(s)`}
            </p>
          </div>
          <Button variant="outline" strong size="lg" fullWidth onClick={reset}>
            CLOSE
          </Button>
        </div>
      )}
    </Modal>
  );
}
