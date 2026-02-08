import {
    Area,
    AreaChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';
import type { DrawdownPoint } from '../../types/analytics.types';
import { formatCurrency, formatPercent } from '../../utils/formatters';

interface DrawdownChartProps {
  data: DrawdownPoint[];
  isLoading: boolean;
}

/** Area chart showing drawdown from equity peak. */
export function DrawdownChart({ data, isLoading }: DrawdownChartProps) {
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
        No drawdown data
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    date: new Date(d.time).toLocaleDateString(),
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis
          tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => formatCurrency(v)}
        />
        <Tooltip
          formatter={(value: number, name: string) => {
            if (name === 'drawdown') return [formatCurrency(value), 'Drawdown'];
            if (name === 'drawdown_pct') return [formatPercent(value), 'DD %'];
            return [value, name];
          }}
          labelStyle={{ fontWeight: 600 }}
        />
        <Area
          type="monotone"
          dataKey="drawdown"
          stroke="#ef4444"
          fill="#fecaca"
          strokeWidth={1.5}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
