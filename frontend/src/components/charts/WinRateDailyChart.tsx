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
import type { EquityCurvePoint } from '../../types/analytics.types';
import { formatPercent } from '../../utils/formatters';

interface WinRateDailyChartProps {
  data: EquityCurvePoint[];
  isLoading: boolean;
}

/** Daily Win Rate histogram. */
export function WinRateDailyChart({ data, isLoading }: WinRateDailyChartProps) {
  if (isLoading) {
    return (
      <div className="h-64 flex items-center justify-center bg-gray-50 rounded-lg animate-pulse">
        <div className="h-4 w-32 bg-gray-200 rounded" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
        No win rate data
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString(),
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
        <XAxis dataKey="displayDate" tick={{ fontSize: 11 }} />
        <YAxis
          tick={{ fontSize: 11 }}
          domain={[0, 100]}
          tickFormatter={(v: number) => formatPercent(v, 0)}
        />
        <Tooltip
          formatter={(value: number) => [formatPercent(value), 'Win Rate']}
          labelStyle={{ fontWeight: 600 }}
        />
        <ReferenceLine y={50} stroke="#9ca3af" strokeDasharray="3 3" />
        <Bar
          dataKey="win_rate"
          name="win_rate"
          barSize={12}
          isAnimationActive={false}
        >
          {chartData.map((entry) => (
            <Cell
              key={entry.date}
              fill={entry.win_rate >= 50 ? '#22c55e' : '#ef4444'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
