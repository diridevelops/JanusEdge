import { endOfMonth, format, startOfMonth } from 'date-fns';
import { useCallback, useEffect, useState } from 'react';

import { getCalendar, getSummary } from '../api/analytics.api';
import { CalendarHeatmap } from '../components/charts/CalendarHeatmap';
import { FilterBar } from '../components/filters/FilterBar';
import type { AnalyticsSummary, CalendarDay } from '../types/analytics.types';
import { formatCurrency, formatPercent } from '../utils/formatters';

/** Calendar heatmap page — daily P&L heatmap with summary stats. */
export function CalendarPage() {
  const [filters, setFilters] = useState({
    symbol: '',
    side: '',
    account: '',
    tag: '',
  });
  const [visibleMonth, setVisibleMonth] = useState<Date>(() => startOfMonth(new Date()));
  const [loading, setLoading] = useState(true);
  const [calendar, setCalendar] = useState<CalendarDay[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);

  type Filters = typeof filters;
  const fetchData = useCallback(async (f: Filters, month: Date) => {
    setLoading(true);
    const apiFilters = Object.fromEntries(
      Object.entries(f).filter(([, v]) => v !== '')
    );
    const monthFilters = {
      ...apiFilters,
      date_from: format(startOfMonth(month), 'yyyy-MM-dd'),
      date_to: format(endOfMonth(month), 'yyyy-MM-dd'),
    };
    try {
      const [calendarRes, summaryRes] = await Promise.all([
        getCalendar(monthFilters),
        getSummary(monthFilters),
      ]);
      setCalendar(calendarRes);
      setSummary(summaryRes);
    } catch {
      // Errors handled by Axios interceptor
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData(filters, visibleMonth);
  }, [filters, fetchData, visibleMonth]);

  function handleFilterChange(key: string, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  function handleClearFilters() {
    setFilters({ symbol: '', side: '', account: '', tag: '' });
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Calendar</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          See your monthly trading performance at a glance.
        </p>
      </div>

      {/* Filters */}
      <FilterBar
        filters={{ ...filters, date_from: '', date_to: '' }}
        onFilterChange={handleFilterChange}
        onClearFilters={handleClearFilters}
        showDateFilters={false}
      />

      {/* Quick stats bar */}
      {summary && !loading && (
        <section className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-600 dark:text-gray-400">
            Monthly stats
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            <div className="card p-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">Total Trades</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">{summary.total_trades}</p>
            </div>
            <div className="card p-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">Net P&L</p>
              <p className={`text-lg font-semibold ${summary.total_net_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                {formatCurrency(summary.total_net_pnl)}
              </p>
            </div>
            <div className="card p-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">Win Rate</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">{formatPercent(summary.win_rate)}</p>
            </div>
            <div className="card p-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">Net Profit Factor ($)</p>
              <p
                className={`text-lg font-semibold ${
                  summary.profit_factor != null && summary.profit_factor >= 1 ? 'text-profit' : 'text-loss'
                }`}
              >
                {summary.profit_factor != null ? summary.profit_factor.toFixed(2) : 'N/A'}
              </p>
            </div>
            <div className="card p-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">W:L Ratio (R)</p>
              <p
                className={`text-lg font-semibold ${
                  summary.wl_ratio_r != null && summary.wl_ratio_r >= 1 ? 'text-profit' : 'text-loss'
                }`}
              >
                {summary.wl_ratio_r != null ? summary.wl_ratio_r.toFixed(2) : 'N/A'}
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Calendar heatmap */}
      <div className="card p-4">
        <CalendarHeatmap
          data={calendar}
          isLoading={loading}
          visibleMonth={visibleMonth}
          onVisibleMonthChange={setVisibleMonth}
        />
      </div>
    </div>
  );
}
