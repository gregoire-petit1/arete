import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { cn } from '@/lib/utils';

interface LoadDataPoint {
  date: string;
  load: number;
  zone?: string;
}

interface LoadChartProps {
  data: LoadDataPoint[];
  showAcute?: boolean;
  showChronic?: boolean;
  acuteLoad?: number;
  chronicLoad?: number;
}

// Custom tooltip with dark theme
function CustomTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ value: number; dataKey: string }>;
  label?: string;
}) {
  if (!active || !payload || !payload.length) return null;

  return (
    <div className="glass-panel p-3 border border-neon-cyan/30">
      <div className="text-xs text-text-muted font-mono mb-1">{label}</div>
      <div className="text-lg text-neon-cyan font-mono font-bold">
        {payload[0].value.toFixed(0)}
      </div>
      <div className="text-xs text-text-muted">Load Units</div>
    </div>
  );
}

export function LoadChart({
  data,
  showAcute = true,
  showChronic = true,
  acuteLoad,
  chronicLoad,
}: LoadChartProps) {
  // Calculate 7-day and 28-day averages if not provided
  const acute = acuteLoad ?? (data.slice(-7).reduce((sum, d) => sum + d.load, 0) / 7);
  const chronic = chronicLoad ?? (data.slice(-28).reduce((sum, d) => sum + d.load, 0) / Math.min(28, data.length));

  return (
    <div className="w-full h-[200px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="loadGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#00F0FF" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#00F0FF" stopOpacity={0} />
            </linearGradient>
          </defs>
          
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#606060', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            tickFormatter={(value) => {
              const date = new Date(value);
              return date.toLocaleDateString('fr-FR', { weekday: 'short' }).charAt(0).toUpperCase();
            }}
          />
          
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#606060', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            width={40}
          />
          
          <Tooltip content={<CustomTooltip />} />
          
          {showAcute && (
            <ReferenceLine
              y={acute}
              stroke="#00F0FF"
              strokeDasharray="3 3"
              strokeOpacity={0.5}
            />
          )}
          
          {showChronic && (
            <ReferenceLine
              y={chronic}
              stroke="#9D4EDD"
              strokeDasharray="3 3"
              strokeOpacity={0.5}
            />
          )}
          
          <Area
            type="monotone"
            dataKey="load"
            stroke="#00F0FF"
            strokeWidth={2}
            fill="url(#loadGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// Mini sparkline version for compact display
interface SparklineProps {
  data: number[];
  className?: string;
}

export function LoadSparkline({ data, className }: SparklineProps) {
  const chartData = data.map((load, idx) => ({ idx, load }));
  
  return (
    <div className={cn('w-full h-[40px]', className)}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id="sparkGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#00F0FF" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#00F0FF" stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="load"
            stroke="#00F0FF"
            strokeWidth={1}
            fill="url(#sparkGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
