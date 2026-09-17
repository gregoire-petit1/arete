import type { ActualSession, PlannedSession } from '@/types';

export type PlannedState = 'done' | 'missed' | 'pending' | 'skipped';

export interface DayLink {
  /** Planned session + the realised session that fulfils it, when there is one. */
  planned: { session: PlannedSession; realised: ActualSession | null; state: PlannedState }[];
  /** Realised sessions that no planned session of the day explains. */
  offPlan: ActualSession[];
}

const day = (iso: string) => iso.slice(0, 10);

/**
 * Pair the planned sessions of a day with what was actually done.
 *
 * A realised session fulfils a planned one when the backend linked them
 * (`planned_session_id`) or, failing that, when it shares the sport and the day.
 * Each realised session is consumed once, so two runs on a day with one planned
 * run leave the second one "off plan".
 */
export function linkDay(
  date: string,
  planned: PlannedSession[],
  actual: ActualSession[],
  today: string
): DayLink {
  const candidates = actual.filter((a) => day(a.date) === date);
  const used = new Set<number>();

  const pick = (p: PlannedSession): ActualSession | null => {
    const linked = candidates.find((a) => a.planned_session_id === p.id && !used.has(a.id));
    const sameSport = candidates.find((a) => a.sport === p.sport && !used.has(a.id));
    const match = linked ?? sameSport ?? null;
    if (match) used.add(match.id);
    return match;
  };

  const rows = planned.map((session) => {
    const realised = pick(session);
    let state: PlannedState;
    if (session.status === 'skipped') state = 'skipped';
    else if (session.status === 'completed' || realised) state = 'done';
    else state = date < today ? 'missed' : 'pending';
    return { session, realised, state };
  });

  return { planned: rows, offPlan: candidates.filter((a) => !used.has(a.id)) };
}

/** Week-level counts for the adherence panel (due = up to today). */
export function weekStats(
  days: string[],
  planned: PlannedSession[],
  actual: ActualSession[],
  today: string
) {
  let done = 0;
  let missed = 0;
  let due = 0;
  let offPlan = 0;
  for (const date of days) {
    const link = linkDay(
      date,
      planned.filter((p) => p.date === date),
      actual,
      today
    );
    for (const row of link.planned) {
      if (date > today) continue;
      due += 1;
      if (row.state === 'done') done += 1;
      else if (row.state === 'missed' || row.state === 'skipped') missed += 1;
    }
    offPlan += link.offPlan.length;
  }
  return { done, missed, due, offPlan, rate: due ? Math.round((done / due) * 100) : 0 };
}
