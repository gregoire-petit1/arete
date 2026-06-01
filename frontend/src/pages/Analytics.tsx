import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, LineChart, Line, ScatterChart, Scatter,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts';
import { analyticsApi } from '@/lib/api';

const PERIODS = ['7d', '30d', '90d', '6m', '1y', 'all'] as const;
type Period = (typeof PERIODS)[number];

const SPORT_COLORS: Record<string, string> = {
  run: '#00f0ff',
  running: '#00f0ff',
  ride: '#ff6b35',
  cycling: '#ff6b35',
  swim: '#3b82f6',
  swimming: '#3b82f6',
  walk: '#22c55e',
  walking: '#22c55e',
  weight_training: '#a855f7',
  strength: '#a855f7',
  other: '#6b7280',
};

function ChartCard({
  title,
  children,
  loading,
  empty,
}: {
  title: string;
  children: React.ReactNode;
  loading?: boolean;
  empty?: boolean;
}) {
  return (
    <div className="bg-abyss rounded-lg border border-text-muted/20 p-4">
      <h3 className="text-sm font-mono text-neon-cyan mb-3 uppercase tracking-wider">
        {title}
      </h3>
      {loading ? (
        <div className="h-[300px] flex items-center justify-center text-text-muted animate-pulse">
          Loading...
        </div>
      ) : empty ? (
        <div className="h-[300px] flex items-center justify-center text-text-muted text-sm">
          No data for this period
        </div>
      ) : (
        children
      )}
    </div>
  );
}

function formatPace(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// ── Volume Chart ──────────────────────────────────────────
function VolumeChart({ period }: { period: Period }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'volume', period],
    queryFn: () => analyticsApi.getVolume(period),
  });

  // Backend returns {weeks: [{week, sports: {run: {hours, km}}, total_hours}]}
  // Flatten to [{week, run: 1.5, weight_training: 2.0}] for Recharts
  const rawWeeks: any[] = data?.weeks ?? data?.data ?? [];
  const volumeData = rawWeeks.map((w: any) => {
    const flat: Record<string, any> = { week: w.week };
    if (w.sports && typeof w.sports === 'object') {
      for (const [sport, val] of Object.entries(w.sports)) {
        flat[sport] = (val as any)?.hours ?? val ?? 0;
      }
    }
    return flat;
  });
  // Collect all sport names across all weeks
  const sportsSet = new Set<string>();
  volumeData.forEach((w) => Object.keys(w).filter((k) => k !== 'week').forEach((k) => sportsSet.add(k)));
  const sports = Array.from(sportsSet);

  return (
    <ChartCard title="Training Volume" loading={isLoading} empty={volumeData.length === 0}>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={volumeData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="week" stroke="#888" tick={{ fontSize: 12 }} />
          <YAxis stroke="#888" />
          <Tooltip contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333', color: '#ccc' }} />
          <Legend />
          {sports.map((sport) => (
            <Bar
              key={sport}
              dataKey={sport}
              stackId="volume"
              fill={SPORT_COLORS[sport] || '#6b7280'}
              name={sport}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Training Load Chart ───────────────────────────────────
function TrainingLoadChart({ period }: { period: Period }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'training-load', period],
    queryFn: () => analyticsApi.getTrainingLoad(period),
  });

  const loadData = data?.data ?? [];

  return (
    <ChartCard title="Training Load (PMC)" loading={isLoading} empty={!Array.isArray(loadData) || loadData.length === 0}>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={loadData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="date" stroke="#888" tick={{ fontSize: 12 }} />
          <YAxis stroke="#888" />
          <Tooltip contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333', color: '#ccc' }} />
          <Legend />
          <Line type="monotone" dataKey="ctl" stroke="#3b82f6" name="Fitness (CTL)" dot={false} />
          <Line type="monotone" dataKey="atl" stroke="#ef4444" name="Fatigue (ATL)" dot={false} />
          <Line type="monotone" dataKey="tsb" stroke="#22c55e" name="Form (TSB)" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Pace Chart ────────────────────────────────────────────
function PaceChart({ period }: { period: Period }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'pace', period],
    queryFn: () => analyticsApi.getPace(period),
  });

  const paceData = data?.activities ?? data?.data ?? [];

  return (
    <ChartCard title="Pace Trend" loading={isLoading} empty={!Array.isArray(paceData) || paceData.length === 0}>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="date" stroke="#888" tick={{ fontSize: 12 }} name="Date" />
          <YAxis
            dataKey="pace_sec_km"
            stroke="#888"
            reversed
            tickFormatter={(v: number) => formatPace(v)}
            name="Pace"
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333', color: '#ccc' }}
            formatter={(value: number, name: string) => [formatPace(value), name === 'pace_sec_km' ? 'Pace' : name]}
          />
          <Scatter data={paceData} fill="#00f0ff" />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── HR Zones Chart ────────────────────────────────────────
const ZONE_COLORS = ['#3b82f6', '#22c55e', '#eab308', '#f97316', '#ef4444'];

function HRZonesChart({ period }: { period: Period }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'hr-zones', period],
    queryFn: () => analyticsApi.getHrZones(period),
  });

  // Backend returns {weeks: [{week, zones: {z1: 600, z2: 1200, ...}}]}
  // Flatten to [{week, z1: 10, z2: 20, ...}] with minutes for Recharts
  const rawZones: any[] = data?.weeks ?? data?.data ?? [];
  const zoneData = rawZones.map((w: any) => {
    const flat: Record<string, any> = { week: w.week };
    if (w.zones && typeof w.zones === 'object') {
      for (const [zone, secs] of Object.entries(w.zones)) {
        flat[zone] = Math.round((secs as number) / 60); // seconds -> minutes
      }
    } else {
      // Already flat format
      for (const key of ['z1', 'z2', 'z3', 'z4', 'z5']) {
        if (w[key] != null) flat[key] = Math.round(w[key] / 60);
      }
    }
    return flat;
  });

  return (
    <ChartCard title="Heart Rate Zones" loading={isLoading} empty={!Array.isArray(zoneData) || zoneData.length === 0}>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={zoneData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="week" stroke="#888" tick={{ fontSize: 12 }} />
          <YAxis stroke="#888" label={{ value: 'min', angle: -90, position: 'insideLeft', fill: '#666', fontSize: 10 }} />
          <Tooltip contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333', color: '#ccc' }} />
          <Legend />
          {['z1', 'z2', 'z3', 'z4', 'z5'].map((zone, i) => (
            <Bar key={zone} dataKey={zone} stackId="zones" fill={ZONE_COLORS[i]} name={`Zone ${i + 1}`} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Sport Distribution Chart ──────────────────────────────
function SportDistributionChart({ period }: { period: Period }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'sport-distribution', period],
    queryFn: () => analyticsApi.getSportDistribution(period),
  });

  const sportData = data?.sports ?? data?.data ?? [];

  return (
    <ChartCard title="Sport Distribution" loading={isLoading} empty={!Array.isArray(sportData) || sportData.length === 0}>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={sportData}
            dataKey="hours"
            nameKey="sport"
            innerRadius={60}
            outerRadius={100}
            paddingAngle={2}
          >
            {sportData.map((entry: any, i: number) => (
              <Cell key={i} fill={SPORT_COLORS[entry.sport] || '#6b7280'} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333', color: '#ccc' }} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Best Efforts Table ────────────────────────────────────
function BestEffortsTable() {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'best-efforts'],
    queryFn: () => analyticsApi.getBestEfforts(),
  });

  const efforts = data?.efforts ?? data?.data ?? [];

  return (
    <ChartCard
      title="Best Efforts (Running)"
      loading={isLoading}
      empty={!Array.isArray(efforts) || efforts.length === 0}
    >
      {Array.isArray(efforts) && efforts.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-text-muted/20">
                <th className="text-left py-2 px-2 text-neon-cyan font-mono text-xs uppercase">Effort</th>
                <th className="text-left py-2 px-2 text-neon-cyan font-mono text-xs uppercase">Best Time</th>
                <th className="text-left py-2 px-2 text-neon-cyan font-mono text-xs uppercase">Date</th>
                <th className="text-left py-2 px-2 text-neon-cyan font-mono text-xs uppercase">Activity</th>
              </tr>
            </thead>
            <tbody>
              {efforts.map((e: any, i: number) => (
                <tr key={i} className="border-b border-text-muted/10 hover:bg-void/50">
                  <td className="py-2 px-2 text-text-primary">{e.name ?? e.effort ?? e.distance}</td>
                  <td className="py-2 px-2 text-text-secondary font-mono">{e.best_time_display ?? e.best_time ?? e.time}</td>
                  <td className="py-2 px-2 text-text-muted">{e.date}</td>
                  <td className="py-2 px-2 text-text-muted">{e.activity_name ?? e.activity ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="h-[300px] flex items-center justify-center text-text-muted text-sm text-center px-4">
          No best efforts data yet — sync activities from Strava to get started
        </div>
      )}
    </ChartCard>
  );
}

// ── Cardiac Efficiency Chart ──────────────────────────────
function CardiacEfficiencyChart({ period }: { period: Period }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'cardiac-efficiency', period],
    queryFn: () => analyticsApi.getCardiacEfficiency(period),
  });

  const effData = data?.data ?? [];

  return (
    <ChartCard title="Cardiac Efficiency Trend" loading={isLoading} empty={!Array.isArray(effData) || effData.length === 0}>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={effData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="week" stroke="#888" tick={{ fontSize: 12 }} />
          <YAxis yAxisId="eff" stroke="#00f0ff" domain={['auto', 'auto']} />
          <YAxis yAxisId="hr" orientation="right" stroke="#ef4444" domain={['auto', 'auto']} />
          <Tooltip
            contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333', color: '#ccc' }}
            formatter={(value: number, name: string) => {
              if (name === 'Efficiency') return [value.toFixed(1) + ' bpm/(km/h)', name];
              if (name === 'Avg HR') return [value + ' bpm', name];
              return [value, name];
            }}
            labelFormatter={(label: string) => `Week of ${label}`}
          />
          <Legend />
          <Line yAxisId="eff" type="monotone" dataKey="efficiency" stroke="#00f0ff" name="Efficiency" strokeWidth={2} dot={{ r: 3 }} />
          <Line yAxisId="hr" type="monotone" dataKey="avg_hr" stroke="#ef4444" name="Avg HR" strokeWidth={1} strokeDasharray="5 5" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── HR vs Pace Scatter ────────────────────────────────────
function HrPaceScatter({ period }: { period: Period }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'hr-pace-scatter', period],
    queryFn: () => analyticsApi.getHrPaceScatter(period),
  });

  const sessions = data?.sessions ?? [];
  // Color by elevation bucket
  const colorByElevation = (elev: number | null) => {
    if (elev == null) return '#6b7280';
    if (elev < 50) return '#22c55e';   // flat
    if (elev < 150) return '#eab308';  // moderate
    return '#ef4444';                   // hilly
  };

  return (
    <ChartCard title="HR vs Pace" loading={isLoading} empty={!Array.isArray(sessions) || sessions.length === 0}>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis
            dataKey="pace_sec_km"
            stroke="#888"
            tick={{ fontSize: 12 }}
            reversed
            tickFormatter={(v: number) => formatPace(v)}
            name="Pace"
            label={{ value: 'Pace (min/km)', position: 'insideBottom', offset: -5, fill: '#666', fontSize: 10 }}
          />
          <YAxis
            dataKey="avg_hr"
            stroke="#888"
            name="HR"
            label={{ value: 'Avg HR (bpm)', angle: -90, position: 'insideLeft', fill: '#666', fontSize: 10 }}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333', color: '#ccc' }}
            formatter={(value: number, name: string) => {
              if (name === 'Pace') return [formatPace(value), name];
              if (name === 'HR') return [value + ' bpm', name];
              return [value, name];
            }}
            content={({ payload }) => {
              if (!payload?.[0]?.payload) return null;
              const s = payload[0].payload;
              return (
                <div className="bg-[#1a1a2e] border border-[#333] p-2 text-xs text-gray-300 rounded">
                  <div className="font-mono text-neon-cyan">{s.name}</div>
                  <div>{s.date} · {s.sport}</div>
                  <div>Pace: {s.pace_display} · HR: {s.avg_hr} bpm</div>
                  <div>D+: {s.elevation_gain ?? '—'}m · {s.distance_km ?? '—'} km</div>
                </div>
              );
            }}
          />
          <Scatter data={sessions} shape="circle">
            {sessions.map((s: any, i: number) => (
              <Cell key={i} fill={colorByElevation(s.elevation_gain)} fillOpacity={0.8} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-2 text-xs text-text-muted justify-center">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#22c55e] inline-block" /> Flat (&lt;50m)</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#eab308] inline-block" /> Moderate</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#ef4444] inline-block" /> Hilly (&gt;150m)</span>
      </div>
    </ChartCard>
  );
}

// ── HR vs Elevation Scatter ───────────────────────────────
function HrElevationScatter({ period }: { period: Period }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'hr-pace-scatter', period],
    queryFn: () => analyticsApi.getHrPaceScatter(period),
  });

  const sessions = (data?.sessions ?? []).filter((s: any) => s.elevation_gain != null);

  return (
    <ChartCard title="HR vs Elevation" loading={isLoading} empty={sessions.length === 0}>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis
            dataKey="elevation_gain"
            stroke="#888"
            tick={{ fontSize: 12 }}
            name="Elevation"
            label={{ value: 'D+ (m)', position: 'insideBottom', offset: -5, fill: '#666', fontSize: 10 }}
          />
          <YAxis
            dataKey="avg_hr"
            stroke="#888"
            name="HR"
            label={{ value: 'Avg HR (bpm)', angle: -90, position: 'insideLeft', fill: '#666', fontSize: 10 }}
          />
          <Tooltip
            content={({ payload }) => {
              if (!payload?.[0]?.payload) return null;
              const s = payload[0].payload;
              return (
                <div className="bg-[#1a1a2e] border border-[#333] p-2 text-xs text-gray-300 rounded">
                  <div className="font-mono text-neon-cyan">{s.name}</div>
                  <div>{s.date} · {s.sport}</div>
                  <div>D+: {s.elevation_gain}m · HR: {s.avg_hr} bpm</div>
                  <div>{s.distance_km ?? '—'} km · {s.pace_display ?? '—'}</div>
                </div>
              );
            }}
          />
          <Scatter data={sessions} fill="#a855f7" fillOpacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Main Page ─────────────────────────────────────────────
export function AnalyticsPage() {
  const [period, setPeriod] = useState<Period>('30d');

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      {/* Header + Period Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-xl font-bold font-mono text-neon-cyan tracking-wider uppercase">
          Analytics
        </h1>
        <div className="flex gap-1 flex-wrap">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 text-xs font-mono rounded transition-all ${
                period === p
                  ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/40'
                  : 'text-text-muted hover:text-text-secondary bg-abyss border border-text-muted/20'
              }`}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <VolumeChart period={period} />
        <TrainingLoadChart period={period} />
        <PaceChart period={period} />
        <HRZonesChart period={period} />
        <SportDistributionChart period={period} />
        <BestEffortsTable />
      </div>

      {/* Cardiac Analysis Section */}
      <h2 className="text-lg font-bold font-mono text-neon-cyan/80 tracking-wider uppercase pt-2">
        Cardiac Analysis
      </h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CardiacEfficiencyChart period={period} />
        <HrPaceScatter period={period} />
        <HrElevationScatter period={period} />
      </div>
    </div>
  );
}
