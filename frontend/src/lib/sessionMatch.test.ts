import { describe, expect, it } from 'vitest';
import type { ActualSession, PlannedSession } from '@/types';
import { linkDay, weekStats } from './sessionMatch';

const planned = (over: Partial<PlannedSession> = {}): PlannedSession => ({
  id: 1,
  date: '2026-10-09',
  sport: 'running',
  session_type: 'endurance',
  target_duration_min: 45,
  target_distance_km: null,
  target_hr_zone: 'Z2',
  target_intensity: 'easy',
  description: null,
  source: 'manual',
  status: 'pending',
  garmin_workout_id: null,
  garmin_pushed_at: null,
  ...over,
});

const run = (over: Partial<ActualSession> = {}): ActualSession =>
  ({
    id: 10,
    planned_session_id: null,
    date: '2026-10-09',
    sport: 'running',
    duration_sec: 2700,
    ...over,
  }) as ActualSession;

describe('a session the morning adaptation modified', () => {
  const modified = planned({ status: 'modified', session_type: 'recovery' });

  it('is still to do today until something is done', () => {
    const link = linkDay('2026-10-09', [modified], [], '2026-10-09');
    expect(link.planned[0].state).toBe('pending');
  });

  it('is missed once its day has passed without a session', () => {
    const link = linkDay('2026-10-09', [modified], [], '2026-10-10');
    expect(link.planned[0].state).toBe('missed');
  });

  it('is done by a realised session of the same sport', () => {
    const link = linkDay('2026-10-09', [modified], [run()], '2026-10-09');
    expect(link.planned[0]).toMatchObject({ state: 'done', realised: { id: 10 } });
    expect(link.offPlan).toEqual([]);
  });

  it('counts as due, not as done, in the week stats', () => {
    const stats = weekStats(['2026-10-09'], [modified], [], '2026-10-09');
    expect(stats).toMatchObject({ due: 1, done: 0, missed: 0 });
  });
});
