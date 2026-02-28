import { useCallback, useEffect, useState } from 'react';

import {
    getApptByDayOfWeek,
    getApptByTimeframe,
    getByTag,
    getDrawdown,
    getEquityCurve,
    getSummary,
    getTradePnls,
} from '../api/analytics.api';
import { EvolutionTab } from '../components/analytics/EvolutionTab';
import { MonteCarloSimulator } from '../components/analytics/MonteCarloSimulator';
import { StatsGrid } from '../components/analytics/StatsGrid';
import { APPTDailyChart } from '../components/charts/APPTDailyChart';
import { DayOfWeekAPPTChart } from '../components/charts/DayOfWeekAPPTChart';
import { DrawdownChart } from '../components/charts/DrawdownChart';
import { EquityCurveChart } from '../components/charts/EquityCurveChart';
import { TimeframeAPPTChart } from '../components/charts/TimeframeAPPTChart';
import { WinRateDailyChart } from '../components/charts/WinRateDailyChart';
import { FilterBar } from '../components/filters/FilterBar';
import { useAuth } from '../hooks/useAuth';
import type {
    AnalyticsSummary,
    ApptByDayOfWeekEntry,
    ApptByTimeframeEntry,
    DrawdownPoint,
    EquityCurvePoint,
    TagAnalytics,
    TradePnl,
} from '../types/analytics.types';
import { formatCurrency, formatPercent } from '../utils/formatters';

type AnalyticsTab = 'overview' | 'time-date' | 'evolution' | 'simulator';

/** Analytics dashboard with charts and summary metrics. */
export function AnalyticsPage() {
  const { user } = useAuth();
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
  const [apptByDayOfWeek, setApptByDayOfWeek] = useState<ApptByDayOfWeekEntry[]>([]);
  const [apptByTimeframe, setApptByTimeframe] = useState<ApptByTimeframeEntry[]>([]);
  const [tagAnalytics, setTagAnalytics] = useState<TagAnalytics[]>([]);
  const [tradePnls, setTradePnls] = useState<TradePnl[]>([]);
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('overview');

  type Filters = typeof filters;
  const fetchData = useCallback(async (f: Filters) => {
    setLoading(true);
    // Strip empty strings so the API doesn't receive blank params
    const apiFilters = Object.fromEntries(
      Object.entries(f).filter(([, v]) => v !== '')
    );
    const displayTimezone = user?.display_timezone ?? user?.timezone;
    try {
      const [
        summaryRes,
        equityRes,
        drawdownRes,
        dayOfWeekRes,
        timeframeRes,
        tagRes,
        tradePnlsRes,
      ] = await Promise.all([
        getSummary(apiFilters),
        getEquityCurve(apiFilters),
        getDrawdown(apiFilters),
        getApptByDayOfWeek(apiFilters, displayTimezone),
        getApptByTimeframe(apiFilters, displayTimezone),
        getByTag(apiFilters),
        getTradePnls(apiFilters),
      ]);

      setSummary(summaryRes);
      setEquityCurve(equityRes);
      setDrawdown(drawdownRes);
      setApptByDayOfWeek(dayOfWeekRes);
      setApptByTimeframe(timeframeRes);
      setTagAnalytics(tagRes);
      setTradePnls(tradePnlsRes);
    } catch {
      // Toast handled by Axios interceptor for 401; silent catch otherwise
    } finally {
      setLoading(false);
    }
  }, [user?.display_timezone, user?.timezone]);

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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Analytics</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Detailed performance metrics and visual analysis of your trading.
        </p>
      </div>

      {/* Filters */}
      <FilterBar filters={filters} onFilterChange={handleFilterChange} onClearFilters={handleClearFilters} />

      {/* Summary metrics */}
      <StatsGrid
        summary={summary}
        drawdown={drawdown}
        isLoading={loading}
      />

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-2" aria-label="Analytics tabs">
          <button
            type="button"
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-2 text-sm font-medium rounded-t-md border border-b-0 ${
              activeTab === 'overview'
                ? 'bg-white text-gray-900 border-gray-300 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-600'
                : 'bg-gray-100 text-gray-600 border-transparent hover:text-gray-800 dark:bg-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            Overview
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('time-date')}
            className={`px-4 py-2 text-sm font-medium rounded-t-md border border-b-0 ${
              activeTab === 'time-date'
                ? 'bg-white text-gray-900 border-gray-300 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-600'
                : 'bg-gray-100 text-gray-600 border-transparent hover:text-gray-800 dark:bg-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            Time & Date
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('evolution')}
            className={`px-4 py-2 text-sm font-medium rounded-t-md border border-b-0 ${
              activeTab === 'evolution'
                ? 'bg-white text-gray-900 border-gray-300 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-600'
                : 'bg-gray-100 text-gray-600 border-transparent hover:text-gray-800 dark:bg-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            Evolution
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('simulator')}
            className={`px-4 py-2 text-sm font-medium rounded-t-md border border-b-0 ${
              activeTab === 'simulator'
                ? 'bg-white text-gray-900 border-gray-300 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-600'
                : 'bg-gray-100 text-gray-600 border-transparent hover:text-gray-800 dark:bg-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            Simulator
          </button>
        </nav>
      </div>

      {activeTab === 'overview' && (
        <>
          {/* Equity curve + drawdown row */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="card p-4">
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                Equity Curve
              </h2>
              <EquityCurveChart data={equityCurve} isLoading={loading} />
            </div>

            <div className="card p-4">
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                Drawdown
              </h2>
              <DrawdownChart data={drawdown} isLoading={loading} />
            </div>
          </div>

          {/* APPT daily + Win rate daily row */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="card p-4">
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                APPT (Daily)
              </h2>
              <APPTDailyChart data={equityCurve} isLoading={loading} />
            </div>

            <div className="card p-4">
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                Win Rate (Daily)
              </h2>
              <WinRateDailyChart data={equityCurve} isLoading={loading} />
            </div>
          </div>

          {/* Tag performance table */}
          <div className="card p-4">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Performance by Tag
            </h2>
            {loading ? (
              <div className="h-24 flex items-center justify-center">
                <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
              </div>
            ) : tagAnalytics.length === 0 ? (
              <p className="text-sm text-gray-400 dark:text-gray-500">No tagged trades found.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      <th className="py-2 pr-4">Tag</th>
                      <th className="py-2 pr-4 text-right">Trades</th>
                      <th className="py-2 pr-4 text-right">Net P&L</th>
                      <th className="py-2 pr-4 text-right">Avg P&L</th>
                      <th className="py-2 pr-4 text-right">Win Rate</th>
                      <th className="py-2 text-right">Profit Factor</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                    {tagAnalytics.map((tag) => (
                      <tr key={tag.tag_id}>
                        <td className="py-2 pr-4 font-medium text-gray-800 dark:text-gray-200">
                          {tag.tag_name}
                        </td>
                        <td className="py-2 pr-4 text-right text-gray-600 dark:text-gray-400">
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
                        <td className="py-2 pr-4 text-right text-gray-600 dark:text-gray-400">
                          {formatPercent(tag.win_rate)}
                        </td>
                        <td className="py-2 text-right text-gray-600 dark:text-gray-400">
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
        </>
      )}

      {activeTab === 'time-date' && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <div className="card p-4">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Group by Day of Week (APPT)
            </h2>
            <DayOfWeekAPPTChart
              data={apptByDayOfWeek}
              isLoading={loading}
            />
          </div>

          <div className="card p-4">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Group by Timeframe (APPT)
            </h2>
            <TimeframeAPPTChart
              data={apptByTimeframe}
              isLoading={loading}
            />
          </div>
        </div>
      )}

      {activeTab === 'evolution' && (
        <EvolutionTab filters={filters} />
      )}

      {activeTab === 'simulator' && (
        <MonteCarloSimulator summary={summary} tradePnls={tradePnls} />
      )}
    </div>
  );
}
