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
    date_from: '',
    date_to: '',
  });
  const [loading, setLoading] = useState(true);
  const [calendar, setCalendar] = useState<CalendarDay[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);

  type Filters = typeof filters;
  const fetchData = useCallback(async (f: Filters) => {
    setLoading(true);
    const apiFilters = Object.fromEntries(
      Object.entries(f).filter(([, v]) => v !== '')
    );
    try {
      const [calendarRes, summaryRes] = await Promise.all([
        getCalendar(apiFilters),
        getSummary(apiFilters),
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
    void fetchData(filters);
  }, [filters, fetchData]);

  function handleFilterChange(key: string, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  function handleClearFilters() {
    setFilters({ symbol: '', side: '', account: '', tag: '', date_from: '', date_to: '' });
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Calendar</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Daily P&L heatmap — see your trading performance at a glance.
        </p>
      </div>

      {/* Filters */}
      <FilterBar filters={filters} onFilterChange={handleFilterChange} onClearFilters={handleClearFilters} />

      {/* Quick stats bar */}
      {summary && !loading && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
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
            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase">Profit Factor</p>
            <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {summary.profit_factor != null ? summary.profit_factor.toFixed(2) : '—'}
            </p>
          </div>
        </div>
      )}

      {/* Calendar heatmap */}
      <div className="card p-4">
        <CalendarHeatmap data={calendar} isLoading={loading} />
      </div>
    </div>
  );
}
