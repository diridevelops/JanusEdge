import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useChartColors } from '../../hooks/useChartColors';
import type { RunningPnLPoint } from '../../types/trade.types';
import {
  formatCurrency,
  formatDateTimeWithTimeZone,
} from '../../utils/formatters';

interface RunningPnLChartProps {
  data: RunningPnLPoint[];
  isLoading: boolean;
  displayTimezone?: string;
  emptyStateMessage?: string;
}

function formatAxisLabel(
  isoString: string,
  timezone?: string,
  includeDate = false
): string {
  const options: Intl.DateTimeFormatOptions = includeDate
    ? {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      }
    : {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      };

  if (timezone) {
    options.timeZone = timezone;
  }

  return new Date(isoString).toLocaleString('en-US', options);
}

/** Filled area chart for one trade's running gross P&L over time. */
export function RunningPnLChart({
  data,
  isLoading,
  displayTimezone,
  emptyStateMessage,
}: RunningPnLChartProps) {
  const c = useChartColors();

  const firstDay = data[0]?.time.slice(0, 10);
  const spansMultipleDays = data.some(
    (point) => point.time.slice(0, 10) !== firstDay
  );
  const chartData = data.map((point) => ({
    ...point,
    positivePnl: point.pnl >= 0 ? point.pnl : null,
    negativePnl: point.pnl <= 0 ? point.pnl : null,
  }));

  return (
    <div className="relative h-64 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/70 dark:bg-gray-900/70 z-10">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
        </div>
      )}
      {!chartData.length && !isLoading && (
        <div className="absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-gray-400 dark:text-gray-500">
          {emptyStateMessage ?? 'No running P&L data'}
        </div>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={c.grid} />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 11, fill: c.tick }}
            tickFormatter={(value: string) =>
              formatAxisLabel(value, displayTimezone, spansMultipleDays)
            }
            minTickGap={24}
          />
          <YAxis
            tick={{ fontSize: 11, fill: c.tick }}
            tickFormatter={(value: number) => formatCurrency(value)}
          />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) {
                return null;
              }

              const point = payload[0]?.payload as RunningPnLPoint | undefined;
              if (!point) {
                return null;
              }

              return (
                <div
                  style={{
                    backgroundColor: c.tooltipBg,
                    border: `1px solid ${c.tooltipBorder}`,
                    color: c.tooltipText,
                    padding: '8px 10px',
                    borderRadius: '6px',
                  }}
                >
                  <div style={{ fontWeight: 600 }}>
                    {formatDateTimeWithTimeZone(
                      String(label ?? point.time),
                      displayTimezone
                    )}
                  </div>
                  <div>{formatCurrency(point.pnl)} Gross P&amp;L</div>
                </div>
              );
            }}
          />
          <ReferenceLine y={0} stroke={c.reference} strokeDasharray="4 4" />
          <Area
            type="monotone"
            dataKey="positivePnl"
            stroke="#16a34a"
            fill={c.isDark ? '#14532d' : '#bbf7d0'}
            strokeWidth={1.5}
          />
          <Area
            type="monotone"
            dataKey="negativePnl"
            stroke="#dc2626"
            fill={c.isDark ? '#7f1d1d' : '#fecaca'}
            strokeWidth={1.5}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
