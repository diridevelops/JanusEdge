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
import { useChartColors } from '../../hooks/useChartColors';
import type { DistributionBucket } from '../../types/analytics.types';
import { formatCurrency } from '../../utils/formatters';

interface PnLHistogramProps {
  data: DistributionBucket[];
  isLoading: boolean;
}

/** Bar chart showing P&L distribution (histogram). */
export function PnLHistogram({ data, isLoading }: PnLHistogramProps) {
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
        No distribution data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={c.grid} />
        <XAxis
          dataKey="bucket"
          tick={{ fontSize: 11, fill: c.tick }}
          tickFormatter={(v: number) => formatCurrency(v)}
        />
        <YAxis tick={{ fontSize: 11, fill: c.tick }} />
        <Tooltip
          formatter={(value: number) => [value, 'Trades']}
          labelFormatter={(label: number) => `${formatCurrency(label)} bucket`}
          labelStyle={{ fontWeight: 600 }}
          contentStyle={{ backgroundColor: c.tooltipBg, borderColor: c.tooltipBorder, color: c.tooltipText }}
        />
        <ReferenceLine x={0} stroke="#9ca3af" strokeDasharray="3 3" />
        <Bar dataKey="count" radius={[2, 2, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.bucket >= 0 ? '#22c55e' : '#ef4444'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
