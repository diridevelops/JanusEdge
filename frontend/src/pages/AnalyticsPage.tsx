import { useCallback, useEffect, useState } from 'react';

import {
    getByTag,
    getCalendar,
    getDrawdown,
    getEquityCurve,
    getSummary,
} from '../api/analytics.api';
import { StatsGrid } from '../components/analytics/StatsGrid';
import { APPTDailyChart } from '../components/charts/APPTDailyChart';
import { CalendarHeatmap } from '../components/charts/CalendarHeatmap';
import { DrawdownChart } from '../components/charts/DrawdownChart';
import { EquityCurveChart } from '../components/charts/EquityCurveChart';
import { WinRateDailyChart } from '../components/charts/WinRateDailyChart';
import { FilterBar } from '../components/filters/FilterBar';
import type {
    AnalyticsSummary,
    CalendarDay,
    DrawdownPoint,
    EquityCurvePoint,
    TagAnalytics,
} from '../types/analytics.types';
import { formatCurrency, formatPercent } from '../utils/formatters';

/** Analytics dashboard with charts and summary metrics. */
export function AnalyticsPage() {
  const [filters, setFilters] = useState({
    symbol: '',
    side: '',
    account: '',
    tag: '',
    date_from: '',
    date_to: '',
  });
  const [loading, setLoading] = useState(true);

  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [equityCurve, setEquityCurve] = useState<EquityCurvePoint[]>([]);
  const [drawdown, setDrawdown] = useState<DrawdownPoint[]>([]);
  const [calendar, setCalendar] = useState<CalendarDay[]>([]);
  const [tagAnalytics, setTagAnalytics] = useState<TagAnalytics[]>([]);

  type Filters = typeof filters;
  const fetchData = useCallback(async (f: Filters) => {
    setLoading(true);
    // Strip empty strings so the API doesn't receive blank params
    const apiFilters = Object.fromEntries(
      Object.entries(f).filter(([, v]) => v !== '')
    );
    try {
      const [
        summaryRes,
        equityRes,
        drawdownRes,
        calendarRes,
        tagRes,
      ] = await Promise.all([
        getSummary(apiFilters),
        getEquityCurve(apiFilters),
        getDrawdown(apiFilters),
        getCalendar(apiFilters),
        getByTag(apiFilters),
      ]);

      setSummary(summaryRes);
      setEquityCurve(equityRes);
      setDrawdown(drawdownRes);
      setCalendar(calendarRes);
      setTagAnalytics(tagRes);
    } catch {
      // Toast handled by Axios interceptor for 401; silent catch otherwise
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
        <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
        <p className="mt-1 text-sm text-gray-500">
          Detailed performance metrics and visual analysis of your trading.
        </p>
      </div>

      {/* Filters */}
      <FilterBar filters={filters} onFilterChange={handleFilterChange} onClearFilters={handleClearFilters} />

      {/* Summary metrics */}
      <StatsGrid summary={summary} isLoading={loading} />

      {/* Equity curve + drawdown row */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Equity Curve
          </h2>
          <EquityCurveChart data={equityCurve} isLoading={loading} />
        </div>

        <div className="card">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Drawdown
          </h2>
          <DrawdownChart data={drawdown} isLoading={loading} />
        </div>
      </div>

      {/* APPT daily + Win rate daily row */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            APPT (Daily)
          </h2>
          <APPTDailyChart data={equityCurve} isLoading={loading} />
        </div>

        <div className="card">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Win Rate (Daily)
          </h2>
          <WinRateDailyChart data={equityCurve} isLoading={loading} />
        </div>
      </div>

      {/* Calendar heatmap */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Calendar Heatmap
        </h2>
        <CalendarHeatmap data={calendar} isLoading={loading} />
      </div>

      {/* Tag performance table */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          Performance by Tag
        </h2>
        {loading ? (
          <div className="h-24 flex items-center justify-center">
            <div className="h-4 w-32 bg-gray-200 rounded animate-pulse" />
          </div>
        ) : tagAnalytics.length === 0 ? (
          <p className="text-sm text-gray-400">No tagged trades found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  <th className="py-2 pr-4">Tag</th>
                  <th className="py-2 pr-4 text-right">Trades</th>
                  <th className="py-2 pr-4 text-right">Net P&L</th>
                  <th className="py-2 pr-4 text-right">Avg P&L</th>
                  <th className="py-2 pr-4 text-right">Win Rate</th>
                  <th className="py-2 text-right">Profit Factor</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {tagAnalytics.map((tag) => (
                  <tr key={tag.tag_id}>
                    <td className="py-2 pr-4 font-medium text-gray-800">
                      {tag.tag_name}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-600">
                      {tag.trade_count}
                    </td>
                    <td
                      className={`py-2 pr-4 text-right font-medium ${
                        tag.net_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'
                      }`}
                    >
                      {formatCurrency(tag.net_pnl)}
                    </td>
                    <td
                      className={`py-2 pr-4 text-right ${
                        tag.avg_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'
                      }`}
                    >
                      {formatCurrency(tag.avg_pnl)}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-600">
                      {formatPercent(tag.win_rate)}
                    </td>
                    <td className="py-2 text-right text-gray-600">
                      {tag.profit_factor != null
                        ? tag.profit_factor.toFixed(2)
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
