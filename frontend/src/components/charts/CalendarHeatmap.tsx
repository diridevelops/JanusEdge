import type { CalendarDay } from '../../types/analytics.types';
import { formatCurrency } from '../../utils/formatters';

interface CalendarHeatmapProps {
  data: CalendarDay[];
  isLoading: boolean;
}

/** Calendar heatmap showing daily P&L. */
export function CalendarHeatmap({ data, isLoading }: CalendarHeatmapProps) {
  if (isLoading) {
    return (
      <div className="h-48 flex items-center justify-center bg-gray-50 rounded-lg animate-pulse">
        <div className="h-4 w-32 bg-gray-200 rounded" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
        No calendar data
      </div>
    );
  }

  // Group data by month
  const months = new Map<string, CalendarDay[]>();
  data.forEach((day) => {
    const monthKey = day.date.substring(0, 7); // YYYY-MM
    if (!months.has(monthKey)) {
      months.set(monthKey, []);
    }
    months.get(monthKey)!.push(day);
  });

  function getColor(netPnl: number): string {
    if (netPnl === 0) return 'bg-gray-100';
    if (netPnl > 0) {
      if (netPnl > 500) return 'bg-green-500 text-white';
      if (netPnl > 200) return 'bg-green-400 text-white';
      if (netPnl > 100) return 'bg-green-300';
      return 'bg-green-200';
    }
    if (netPnl < -500) return 'bg-red-500 text-white';
    if (netPnl < -200) return 'bg-red-400 text-white';
    if (netPnl < -100) return 'bg-red-300';
    return 'bg-red-200';
  }

  return (
    <div className="space-y-4 overflow-x-auto">
      {Array.from(months.entries()).map(([month, days]) => (
        <div key={month}>
          <h4 className="text-xs font-medium text-gray-500 mb-2">
            {new Date(month + '-01').toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'long',
            })}
          </h4>
          <div className="flex flex-wrap gap-1">
            {days.map((day) => (
              <div
                key={day.date}
                className={`w-10 h-10 rounded flex flex-col items-center justify-center text-xs cursor-default ${getColor(day.net_pnl)}`}
                title={`${day.date}: ${formatCurrency(day.net_pnl)} (${day.trade_count} trades)`}
              >
                <span className="font-medium">
                  {new Date(day.date + 'T12:00:00').getDate()}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Legend */}
      <div className="flex items-center gap-3 text-xs text-gray-500 pt-2">
        <span>Loss</span>
        <div className="flex gap-0.5">
          <div className="w-4 h-4 bg-red-500 rounded" />
          <div className="w-4 h-4 bg-red-400 rounded" />
          <div className="w-4 h-4 bg-red-300 rounded" />
          <div className="w-4 h-4 bg-red-200 rounded" />
          <div className="w-4 h-4 bg-gray-100 rounded" />
          <div className="w-4 h-4 bg-green-200 rounded" />
          <div className="w-4 h-4 bg-green-300 rounded" />
          <div className="w-4 h-4 bg-green-400 rounded" />
          <div className="w-4 h-4 bg-green-500 rounded" />
        </div>
        <span>Profit</span>
      </div>
    </div>
  );
}
