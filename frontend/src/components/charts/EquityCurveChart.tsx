import {
    CartesianGrid,
    Line,
    LineChart,
    ReferenceLine,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';
import type { EquityCurvePoint } from '../../types/analytics.types';
import { formatCurrency } from '../../utils/formatters';

interface EquityCurveChartProps {
  data: EquityCurvePoint[];
  isLoading: boolean;
}

/** Line chart showing cumulative P&L over time. */
export function EquityCurveChart({ data, isLoading }: EquityCurveChartProps) {
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
        No equity curve data
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    date: new Date(d.time).toLocaleDateString(),
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis
          tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => formatCurrency(v)}
        />
        <Tooltip
          formatter={(value: number) => [formatCurrency(value), 'Cumulative P&L']}
          labelStyle={{ fontWeight: 600 }}
        />
        <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
        <Line
          type="monotone"
          dataKey="cumulative_pnl"
          stroke="#4f46e5"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
