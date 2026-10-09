import { describe, expect, it } from 'vitest';
import { type ZoneKind, zoneLabel } from './fr';
import { getZoneColor } from './utils';

// Exact enum values of src/arete/features/workload.py and features/fitness.py.
const BACKEND_ZONES: Record<ZoneKind, string[]> = {
  acwr: ['undertrained', 'optimal', 'caution', 'danger'],
  form: ['freshest', 'fresh', 'neutral', 'tired', 'exhausted'],
  readiness: ['optimal', 'good', 'moderate', 'low', 'critical'],
  monotony: ['ideal', 'acceptable', 'high'],
  strain: ['low', 'optimal', 'high', 'critical'],
};

describe('zone labels', () => {
  for (const [kind, zones] of Object.entries(BACKEND_ZONES) as [ZoneKind, string[]][]) {
    it.each(zones)(`translates ${kind} zone %s`, (zone) => {
      const label = zoneLabel(kind, zone);
      expect(label).not.toBe(zone);
      expect(label).not.toBe('inconnu');
    });
  }

  it('names missing and unknown zones', () => {
    expect(zoneLabel('acwr', 'unknown')).toBe('inconnu');
    expect(zoneLabel('monotony', null)).toBe('inconnu');
  });

  it('reads the same value differently per metric', () => {
    expect(zoneLabel('acwr', 'danger')).toBe('zone à risque');
    expect(zoneLabel('form', 'tired')).toBe('fatigué');
    expect(getZoneColor('strain', 'high')).toBe('orange');
    expect(getZoneColor('monotony', 'high')).toBe('red');
  });
});

describe('zone colors', () => {
  it('colors the backend zones by risk', () => {
    expect(getZoneColor('acwr', 'optimal')).toBe('green');
    expect(getZoneColor('acwr', 'caution')).toBe('orange');
    expect(getZoneColor('acwr', 'danger')).toBe('red');
    expect(getZoneColor('form', 'neutral')).toBe('green');
    expect(getZoneColor('form', 'tired')).toBe('orange');
    expect(getZoneColor('form', 'exhausted')).toBe('red');
    expect(getZoneColor('readiness', 'critical')).toBe('red');
  });

  it('keeps unknown zones neutral', () => {
    expect(getZoneColor('acwr', 'unknown')).toBe('cyan');
    expect(getZoneColor('form', undefined)).toBe('cyan');
  });
});
