// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ActivityDetail } from '@/types';
import { analyticsApi } from '@/lib/api';
import { SessionDetailPage } from './SessionDetail';

vi.mock('@/lib/api', () => ({ analyticsApi: { getSessionDetail: vi.fn() } }));

afterEach(cleanup);

const session: ActivityDetail['session'] = {
  id: 12,
  date: '2026-10-08',
  start_time: '2026-10-08T07:30:00',
  sport: 'running',
  session_type: 'running',
  name: 'Fractionné 5×1000',
  duration_sec: 3000,
  moving_time_sec: 2940,
  distance_m: 10200,
  calories: 640,
  avg_hr: 152,
  max_hr: 178,
  avg_pace_sec_km: 290,
  avg_speed_mps: 3.45,
  max_speed_mps: 4.6,
  ascent_m: 40,
  descent_m: 38,
  avg_cadence: 176,
  max_cadence: 190,
  avg_watts: null,
  rpe: 8,
  notes: null,
  source: 'garmin_connect',
  device_name: null,
  planned_session_id: null,
  adherence_score: null,
};

const detail: ActivityDetail = {
  session,
  zones: { z1: 300, z2: 900, z3: 600, z4: 900, z5: 300 },
  laps: [
    { n: 1, duration_sec: 600, distance_m: 1800, speed_mps: 3, pace_sec_km: 333, avg_hr: 135, max_hr: 145, cadence: 170, intensity: 'warmup' },
    { n: 2, duration_sec: 240, distance_m: 1000, speed_mps: 4.17, pace_sec_km: 240, avg_hr: 170, max_hr: 178, cadence: 184, intensity: 'active' },
    { n: 3, duration_sec: 120, distance_m: 380, speed_mps: 3.1, pace_sec_km: 323, avg_hr: 150, max_hr: 168, cadence: 170, intensity: 4 },
  ],
  splits: [],
  intervals: {
    count: 5,
    work_avg_sec: 240,
    rest_avg_sec: 120,
    warmup_sec: 600,
    cooldown_sec: 300,
    pace_cv_pct: 1.2,
    hr_progression_pct: 3.4,
    work: [{ n: 1, lap: 2, duration_sec: 240, distance_m: 1000, pace_sec_km: 240, avg_hr: 170 }],
  },
  metrics: { pace_cv_pct: 18.2, cadence_avg: 176, cadence_cv_pct: 3.1 },
  streams: { t: [0, 10, 20], heart_rate: [120, 140, 150], speed_mps: [3, 3.2, 4], altitude_m: [1000, 1002, 1001] },
  route: [
    [45.9, 6.87],
    [45.91, 6.88],
  ],
  feedback: { text: 'Répétitions régulières, bravo.', source: 'agent', trigger: 'sync', created_at: null },
};

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/log/sessions/:id" element={<SessionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it('shows the summary, the coach, the intervals, the laps, the zones and the route', async () => {
  vi.mocked(analyticsApi.getSessionDetail).mockResolvedValue(detail);
  renderAt('/log/sessions/12');
  expect(await screen.findByText('Fractionné 5×1000')).toBeTruthy();
  expect(analyticsApi.getSessionDetail).toHaveBeenCalledWith(12);
  expect(screen.getByText('Répétitions régulières, bravo.')).toBeTruthy();
  expect(screen.getByText('FRACTIONNÉ DÉTECTÉ')).toBeTruthy();
  expect(screen.getByText('TOURS (3)')).toBeTruthy();
  expect(screen.getByText('Échauffement')).toBeTruthy();
  expect(screen.getByText('Récup')).toBeTruthy();
  expect(screen.getByText('Z2 endurance')).toBeTruthy();
  expect(screen.getByRole('img', { name: /Tracé GPS/ })).toBeTruthy();
  expect(screen.getByText('4:50 /km')).toBeTruthy();
});

it('says why a session without a recording has no curve', async () => {
  vi.mocked(analyticsApi.getSessionDetail).mockResolvedValue({
    ...detail,
    streams: null,
    route: null,
    intervals: null,
    metrics: null,
    feedback: null,
    laps: [],
  });
  renderAt('/log/sessions/12');
  expect(await screen.findByText('PAS DE FLUX POUR CETTE SÉANCE')).toBeTruthy();
  expect(screen.queryByRole('img', { name: /Tracé GPS/ })).toBeNull();
});

it('rejects an id that is not a number without asking the server', () => {
  vi.mocked(analyticsApi.getSessionDetail).mockClear();
  renderAt('/log/sessions/abc');
  expect(screen.getByText('SÉANCE INTROUVABLE')).toBeTruthy();
  expect(analyticsApi.getSessionDetail).not.toHaveBeenCalled();
});
