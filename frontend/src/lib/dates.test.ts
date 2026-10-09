import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseLocalDate, toLocalISODate } from './dates';

describe('parseLocalDate', () => {
  beforeEach(() => {
    // West of UTC, new Date('YYYY-MM-DD') lands on the previous day.
    vi.stubEnv('TZ', 'America/Los_Angeles');
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('keeps the calendar day west of UTC', () => {
    const d = parseLocalDate('2026-03-02');
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(2);
    expect(d.getDate()).toBe(2);
    expect(d.getDay()).toBe(1); // Monday
    expect(new Date('2026-03-02').getDate()).toBe(1);
  });

  it('round-trips through toLocalISODate and ignores a time part', () => {
    expect(toLocalISODate(parseLocalDate('2026-12-31'))).toBe('2026-12-31');
    expect(toLocalISODate(parseLocalDate('2026-10-09T23:30:00'))).toBe('2026-10-09');
  });
});
