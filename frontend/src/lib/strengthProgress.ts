import type { StrengthRecord, StrengthSuggestion } from '@/types';

/** 82.5 -> "82,5 kg"; null (bodyweight) -> "poids du corps". */
export function formatKg(kg: number | null | undefined): string {
  if (kg == null || kg <= 0) return 'poids du corps';
  return `${kg.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} kg`;
}

/** "3 × 8 @ 82,5 kg" (the range, when there is one, in parentheses). */
export function suggestionPrescription(s: StrengthSuggestion): string {
  const load = s.weight_kg != null ? ` @ ${formatKg(s.weight_kg)}` : ' au poids du corps';
  const range = s.rep_range ? ` (fourchette ${s.rep_range})` : '';
  return `${s.sets} × ${s.reps}${load}${range}`;
}

const RECORD_TITLE: Record<StrengthRecord['kind'], string> = {
  weight: 'Charge la plus lourde',
  e1rm: '1RM estimé',
  reps: 'Répétitions à charge égale',
};

export function recordTitle(record: StrengthRecord): string {
  return RECORD_TITLE[record.kind];
}

/** What was lifted, and what it beat. */
export function recordValue(record: StrengthRecord): string {
  if (record.kind === 'reps') {
    const at = record.weight_kg ? ` à ${formatKg(record.weight_kg)}` : ' au poids du corps';
    const before = record.previous != null ? ` (avant : ${record.previous})` : '';
    return `${record.value} rép.${at}${before}`;
  }
  const lift = record.reps ? ` (${formatKg(record.weight_kg)} × ${record.reps})` : '';
  const before = record.previous != null ? `, avant ${formatKg(record.previous)}` : '';
  return `${formatKg(record.value)}${lift}${before}`;
}
