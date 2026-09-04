import { AreaChart, Area, ResponsiveContainer } from 'recharts';
import { cn } from '@/lib/utils';

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
