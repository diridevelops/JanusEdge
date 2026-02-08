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
import type { TimeOfDayEntry } from '../../types/analytics.types';

interface TimeOfDayChartProps {
  data: TimeOfDayEntry[];
  isLoading: boolean;
}

/** Stacked bar chart showing P&L by hour of day. */
export function TimeOfDayChart({ data, isLoading }: TimeOfDayChartProps) {
  if (isLoading) {
    return (
      <div className="h-[220px] flex items-center justify-center bg-gray-50 rounded-lg animate-pulse">
        <div className="h-4 w-32 bg-gray-200 rounded" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-[220px] flex items-center justify-center text-gray-400 text-sm">
        No time-of-day data
      </div>
    );
  }

  // Build full 24-hour set, filling gaps with zeroes
  const hourMap = new Map<number, TimeOfDayEntry>();
  data.forEach((entry) => hourMap.set(entry.hour, entry));

  const hours = Array.from({ length: 24 }, (_, i) => {
    const existing = hourMap.get(i);
    return {
      hour: i,
      label: `${i.toString().padStart(2, '0')}:00`,
      net_pnl: existing?.net_pnl ?? 0,
      trade_count: existing?.trade_count ?? 0,
      win_rate: existing?.win_rate ?? 0,
    };
  });

  // Only show hours that have at least 1 trade in range
  const activeHours = hours.filter((h) => h.trade_count > 0);
  const chartData = activeHours.length > 0 ? activeHours : hours.filter((h) => h.hour >= 6 && h.hour <= 20);

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: '#e5e7eb' }}
        />
        <YAxis
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => `$${v}`}
        />
        <Tooltip
          formatter={(value: number) => [`$${value.toFixed(2)}`, 'Net P&L']}
          labelFormatter={(label: string) => {
            const entry = chartData.find((d) => d.label === label);
            if (!entry) return label;
            return `${label} — ${entry.trade_count} trades, ${(entry.win_rate * 100).toFixed(0)}% WR`;
          }}
          contentStyle={{ fontSize: 12 }}
        />
        <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
        <Bar dataKey="net_pnl" name="Net P&L" radius={[3, 3, 0, 0]}>
          {chartData.map((entry) => (
            <Cell key={entry.hour} fill={entry.net_pnl >= 0 ? '#22c55e' : '#ef4444'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
