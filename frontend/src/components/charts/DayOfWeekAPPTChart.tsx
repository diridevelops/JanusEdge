import {
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    ReferenceLine,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';
import type { ApptByDayOfWeekEntry } from '../../types/analytics.types';
import { formatCurrency } from '../../utils/formatters';

function buildSparseRoundTicks(values: number[]): number[] {
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const maxAbs = Math.max(Math.abs(min), Math.abs(max));

  const step =
    maxAbs >= 100 ? 50 :
    maxAbs >= 50 ? 25 :
    maxAbs >= 20 ? 10 :
    maxAbs >= 10 ? 5 : 1;

  const roundedMin = Math.floor(min / step) * step;
  const roundedMax = Math.ceil(max / step) * step;

  return Array.from(new Set([roundedMin, 0, roundedMax])).sort((a, b) => a - b);
}

interface DayOfWeekAPPTChartProps {
  data: ApptByDayOfWeekEntry[];
  isLoading: boolean;
}

/** Horizontal histogram of APPT grouped by day of week. */
export function DayOfWeekAPPTChart({ data, isLoading }: DayOfWeekAPPTChartProps) {
  if (isLoading) {
    return (
      <div className="h-72 flex items-center justify-center bg-gray-50 rounded-lg animate-pulse">
        <div className="h-4 w-32 bg-gray-200 rounded" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-72 flex items-center justify-center text-gray-400 text-sm">
        No day-of-week APPT data
      </div>
    );
  }

  const ticks = buildSparseRoundTicks(data.map((d) => d.appt));
  const xMin = ticks[0] ?? 0;
  const xMax = ticks[ticks.length - 1] ?? 0;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
        <XAxis
          type="number"
          tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => formatCurrency(v)}
          domain={[xMin, xMax]}
          ticks={ticks}
        />
        <YAxis
          type="category"
          dataKey="day_of_week"
          tick={{ fontSize: 11 }}
          width={90}
        />
        <Tooltip
          formatter={(value: number) => [formatCurrency(value), 'APPT']}
          labelFormatter={(label: string) => label}
          labelStyle={{ fontWeight: 600 }}
        />
        <ReferenceLine x={0} stroke="#9ca3af" strokeDasharray="3 3" />
        <Bar dataKey="appt" name="appt" barSize={16} isAnimationActive={false}>
          {data.map((entry) => (
            <Cell
              key={entry.day_of_week}
              fill={entry.appt >= 0 ? '#22c55e' : '#ef4444'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
