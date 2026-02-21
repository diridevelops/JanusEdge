import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
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

/** Composed chart: cumulative P&L line + daily PnL histogram bars. */
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

  // Add display date and bar fill color based on sign
  const chartData = data.map((d) => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString(),
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
        <XAxis dataKey="displayDate" tick={{ fontSize: 11 }} />
        <YAxis
          yAxisId="left"
          tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => formatCurrency(v)}
        />
        <Tooltip
          formatter={(value: number, name: string) => {
            if (name === 'cumulative_pnl') return [formatCurrency(value), 'Cumulative P&L'];
            if (name === 'daily_pnl') return [formatCurrency(value), 'Daily P&L'];
            return [value, name];
          }}
          labelStyle={{ fontWeight: 600 }}
        />
        <ReferenceLine yAxisId="left" y={0} stroke="#9ca3af" strokeDasharray="3 3" />
        <Bar
          yAxisId="left"
          dataKey="daily_pnl"
          name="daily_pnl"
          barSize={10}
          opacity={0.7}
          isAnimationActive={false}
        >
          {chartData.map((entry) => (
            <Cell
              key={entry.date}
              fill={entry.daily_pnl >= 0 ? '#22c55e' : '#ef4444'}
              fillOpacity={0.55}
            />
          ))}
        </Bar>
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="cumulative_pnl"
          name="cumulative_pnl"
          stroke="#4f46e5"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
