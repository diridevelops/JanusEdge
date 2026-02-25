import {
    Area,
    AreaChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';
import { useChartColors } from '../../hooks/useChartColors';
import type { DrawdownPoint } from '../../types/analytics.types';
import { formatCurrency, formatPercent } from '../../utils/formatters';

interface DrawdownChartProps {
  data: DrawdownPoint[];
  isLoading: boolean;
}

/** Area chart showing drawdown from equity peak. */
export function DrawdownChart({ data, isLoading }: DrawdownChartProps) {
  const c = useChartColors();

  if (isLoading) {
    return (
      <div className="h-64 flex items-center justify-center bg-gray-50 dark:bg-gray-800 rounded-lg animate-pulse">
        <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">
        No drawdown data
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString(),
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={c.grid} />
        <XAxis dataKey="displayDate" tick={{ fontSize: 11, fill: c.tick }} />
        <YAxis
          tick={{ fontSize: 11, fill: c.tick }}
          tickFormatter={(v: number) => formatCurrency(v)}
        />
        <Tooltip
          formatter={(value: number, name: string) => {
            if (name === 'drawdown') return [formatCurrency(value), 'Drawdown'];
            if (name === 'drawdown_pct') return [formatPercent(value), 'DD %'];
            return [value, name];
          }}
          labelStyle={{ fontWeight: 600 }}
          contentStyle={{ backgroundColor: c.tooltipBg, borderColor: c.tooltipBorder, color: c.tooltipText }}
        />
        <Area
          type="monotone"
          dataKey="drawdown"
          stroke="#ef4444"
          fill={c.isDark ? '#7f1d1d' : '#fecaca'}
          strokeWidth={1.5}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
