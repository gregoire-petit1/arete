import { describe, expect, it } from 'vitest';
import { chartRows, formatElapsed, intensityLabel, isFootSport, projectRoute } from './activity';

describe('chartRows', () => {
  const streams = { t: [0, 5, 10], heart_rate: [140, null, 150], speed_mps: [3.2, 0.3, 4] };

  it('draws a pace on foot and drops the stops', () => {
    expect(chartRows(streams, 'running').map((r) => r.pace)).toEqual([313, null, 250]);
  });

  it('draws km/h on a bike', () => {
    expect(chartRows(streams, 'cycling').map((r) => r.pace)).toEqual([11.5, 1.1, 14.4]);
  });

  it('keeps missing samples as gaps', () => {
    expect(chartRows(streams, 'running').map((r) => r.hr)).toEqual([140, null, 150]);
    expect(chartRows({ t: [0] }, 'running')[0]).toEqual({ t: 0, hr: null, pace: null, altitude: null });
  });
});

describe('formatting', () => {
  it('formats elapsed time', () => {
    expect(formatElapsed(65)).toBe('1:05');
    expect(formatElapsed(3725)).toBe('1:02:05');
  });

  it('labels lap intensities in French, raw FIT numbers included', () => {
    expect(intensityLabel('warmup')).toBe('Échauffement');
    expect(intensityLabel(4)).toBe('Récup');
    expect(intensityLabel(5)).toBe('Effort');
    expect(intensityLabel(null)).toBe('—');
  });

  it('knows which sports read as a pace', () => {
    expect(isFootSport('trail_running')).toBe(true);
    expect(isFootSport('hiking')).toBe(true);
    expect(isFootSport('cycling')).toBe(false);
  });
});

describe('projectRoute', () => {
  it('fits the trace in the box, north up, aspect kept', () => {
    const route: [number, number][] = [
      [45.9, 6.87],
      [45.91, 6.87],
      [45.91, 6.88],
    ];
    const out = projectRoute(route, 200, 100, 0);
    expect(out).not.toBeNull();
    const [sx, sy] = out!.start;
    const [ex, ey] = out!.end;
    expect(sy).toBeGreaterThan(ey - 1e-6); // start is south, so lower on screen
    expect(ex).toBeGreaterThan(sx); // finish is east
    for (const pair of out!.points.split(' ')) {
      const [x, y] = pair.split(',').map(Number);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(200);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(100);
    }
  });

  it('needs two points', () => {
    expect(projectRoute([[45.9, 6.87]], 100, 100)).toBeNull();
  });
});
