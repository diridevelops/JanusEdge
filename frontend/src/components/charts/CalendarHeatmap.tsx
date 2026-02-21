import {
  addDays,
  addMonths,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
} from 'date-fns';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { CalendarDay } from '../../types/analytics.types';

interface CalendarHeatmapProps {
  data: CalendarDay[];
  isLoading: boolean;
}

/** Calendar heatmap showing daily P&L. */
export function CalendarHeatmap({ data, isLoading }: CalendarHeatmapProps) {
  const navigate = useNavigate();

  const dataByDate = useMemo(() => {
    const map = new Map<string, CalendarDay>();
    data.forEach((item) => {
      map.set(item.date, item);
    });
    return map;
  }, [data]);

  const initialMonth = useMemo(() => {
    if (data.length === 0) {
      return startOfMonth(new Date());
    }
    const sortedDates = [...data].sort((a, b) => a.date.localeCompare(b.date));
    const latestDay = sortedDates[sortedDates.length - 1];
    if (!latestDay) {
      return startOfMonth(new Date());
    }
    return startOfMonth(parseISO(latestDay.date));
  }, [data]);

  const [visibleMonth, setVisibleMonth] = useState<Date>(initialMonth);

  const maxAbsPnl = useMemo(() => {
    const maxValue = data.reduce(
      (acc, day) => Math.max(acc, Math.abs(day.net_pnl)),
      0
    );
    return maxValue > 0 ? maxValue : 1;
  }, [data]);

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

  const calendarStart = startOfWeek(startOfMonth(visibleMonth), {
    weekStartsOn: 1,
  });
  const calendarEnd = endOfWeek(endOfMonth(visibleMonth), {
    weekStartsOn: 1,
  });

  const days: Date[] = [];
  let current = calendarStart;
  while (current <= calendarEnd) {
    days.push(current);
    current = addDays(current, 1);
  }

  function getColorClass(netPnl: number): string {
    if (netPnl === 0) return 'bg-gray-50 text-gray-700';

    const ratio = Math.abs(netPnl) / maxAbsPnl;
    if (netPnl > 0) {
      if (ratio > 0.75) return 'bg-green-500 text-white';
      if (ratio > 0.45) return 'bg-green-300 text-gray-900';
      return 'bg-green-100 text-gray-900';
    }

    if (ratio > 0.75) return 'bg-red-500 text-white';
    if (ratio > 0.45) return 'bg-red-300 text-gray-900';
    return 'bg-red-100 text-gray-900';
  }

  function handleDayClick(day: Date) {
    const dayKey = format(day, 'yyyy-MM-dd');
    navigate(`/trades?date_from=${dayKey}&date_to=${dayKey}`);
  }

  const weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setVisibleMonth((prev) => subMonths(prev, 1))}
          className="inline-flex items-center justify-center rounded border border-gray-200 p-1.5 text-gray-600 hover:bg-gray-50"
          aria-label="Previous month"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>

        <h3 className="text-sm font-semibold text-gray-800">
          {format(visibleMonth, 'MMMM yyyy')}
        </h3>

        <button
          type="button"
          onClick={() => setVisibleMonth((prev) => addMonths(prev, 1))}
          className="inline-flex items-center justify-center rounded border border-gray-200 p-1.5 text-gray-600 hover:bg-gray-50"
          aria-label="Next month"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-2">
        {weekDays.map((weekDay) => (
          <div key={weekDay} className="text-xs font-medium text-gray-500 text-center">
            {weekDay}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-2">
        {days.map((day) => {
          const dayKey = format(day, 'yyyy-MM-dd');
          const dayData = dataByDate.get(dayKey);
          const tradeCount = dayData?.trade_count ?? 0;
          const pnl = dayData?.net_pnl ?? 0;
          const roundedPnl = Math.round(pnl);
          const inVisibleMonth = isSameMonth(day, visibleMonth);

          return (
            <button
              key={dayKey}
              type="button"
              onClick={() => handleDayClick(day)}
              className={`min-h-24 rounded border p-2 text-left transition hover:ring-1 hover:ring-blue-300 ${getColorClass(pnl)} ${
                inVisibleMonth ? 'border-gray-200' : 'border-transparent opacity-45'
              }`}
              title={`${dayKey} • ${tradeCount} trades • ${roundedPnl >= 0 ? '+' : ''}${roundedPnl}`}
            >
              <div className="text-xs font-semibold">{format(day, 'd')}</div>
              <div className="mt-2 text-[11px] leading-4">Trades: {tradeCount}</div>
              <div className="text-[11px] leading-4">
                P&L: {roundedPnl >= 0 ? '+' : ''}
                {roundedPnl}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
