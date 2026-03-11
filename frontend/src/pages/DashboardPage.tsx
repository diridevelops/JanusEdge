import { ArrowRight, Upload } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  getApptByDayOfWeek,
  getApptByTimeframe,
  getByTag,
  getDrawdown,
  getEquityCurve,
  getSummary,
} from '../api/analytics.api';
import { EvolutionTab } from '../components/analytics/EvolutionTab';
import { APPTDailyChart } from '../components/charts/APPTDailyChart';
import { DayOfWeekAPPTChart } from '../components/charts/DayOfWeekAPPTChart';
import { DrawdownChart } from '../components/charts/DrawdownChart';
import { EquityCurveChart } from '../components/charts/EquityCurveChart';
import { TimeframeAPPTChart } from '../components/charts/TimeframeAPPTChart';
import { WinRateDailyChart } from '../components/charts/WinRateDailyChart';
import { FilterBar } from '../components/filters/FilterBar';
import { Spinner } from '../components/ui/Spinner';
import { useAuth } from '../hooks/useAuth';
import type {
  AnalyticsSummary,
  ApptByDayOfWeekEntry,
  ApptByTimeframeEntry,
  DrawdownPoint,
  EquityCurvePoint,
  TagAnalytics,
} from '../types/analytics.types';
import { formatCurrency, formatPercent } from '../utils/formatters';

type DashboardTab = 'overview' | 'time-date' | 'evolution';

/** Dashboard page — key stats, filters, and tabbed visualizations. */
export function DashboardPage() {
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
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview');

  type Filters = typeof filters;
  const fetchData = useCallback(async (f: Filters) => {
    setLoading(true);
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
      ] = await Promise.all([
        getSummary(apiFilters),
        getEquityCurve(apiFilters),
        getDrawdown(apiFilters),
        getApptByDayOfWeek(apiFilters, displayTimezone),
        getApptByTimeframe(apiFilters, displayTimezone),
        getByTag(apiFilters),
      ]);

      setSummary(summaryRes);
      setEquityCurve(equityRes);
      setDrawdown(drawdownRes);
      setApptByDayOfWeek(dayOfWeekRes);
      setApptByTimeframe(timeframeRes);
      setTagAnalytics(tagRes);
    } catch {
      // Toast handled by Axios interceptor for 401
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

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner />
      </div>
    );
  }

  const hasTrades = summary !== null && summary.total_trades > 0;

  if (!hasTrades) {
    return (
      <div className="flex flex-col items-center justify-center h-96 space-y-4">
        <Upload className="w-16 h-16 text-gray-300 dark:text-gray-600" />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Welcome to TradeLogs</h1>
        <p className="text-gray-500 text-center max-w-md dark:text-gray-400">
          Import your first trades to see analytics, charts, and performance metrics.
        </p>
        <Link to="/import" className="btn-primary inline-flex items-center gap-2">
          Import Trades <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    );
  }

  const statCards = [
    { label: 'Total Trades', value: summary!.total_trades.toString() },
    {
      label: 'Net P&L',
      value: formatCurrency(summary!.total_net_pnl),
      color: summary!.total_net_pnl >= 0 ? 'pnl-positive' : 'pnl-negative',
    },
    { label: 'Win Rate', value: formatPercent(summary!.win_rate) },
    {
      label: 'APPT',
      value: formatCurrency(summary!.appt),
      color: summary!.appt >= 0 ? 'pnl-positive' : 'pnl-negative',
    },
    {
      label: 'Expectancy (R)',
      value: summary!.expectancy_r != null ? `${summary!.expectancy_r.toFixed(2)}R` : '—',
      color: summary!.expectancy_r != null
        ? (summary!.expectancy_r >= 0 ? 'pnl-positive' : 'pnl-negative')
        : undefined,
    },
  ];

  const tabClass = (tab: DashboardTab) =>
    `px-4 py-2 text-sm font-medium rounded-t-md border border-b-0 ${
      activeTab === tab
        ? 'bg-white text-gray-900 border-gray-300 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-600'
        : 'bg-gray-100 text-gray-600 border-transparent hover:text-gray-800 dark:bg-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
    }`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Dashboard</h1>
        <Link
          to="/analytics"
          className="text-sm text-blue-600 hover:underline inline-flex items-center gap-1 dark:text-blue-400"
        >
          View Analytics <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      {/* Filters */}
      <FilterBar filters={filters} onFilterChange={handleFilterChange} onClearFilters={handleClearFilters} />

      {/* Quick stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {statCards.map((card) => (
          <div key={card.label} className="card p-4 text-center">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider dark:text-gray-400">
              {card.label}
            </p>
            <p className={`mt-1 text-xl font-bold ${card.color ?? 'text-gray-900 dark:text-gray-100'}`}>
              {card.value}
            </p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-2" aria-label="Dashboard tabs">
          <button type="button" onClick={() => setActiveTab('overview')} className={tabClass('overview')}>
            Overview
          </button>
          <button type="button" onClick={() => setActiveTab('time-date')} className={tabClass('time-date')}>
            Time &amp; Date
          </button>
          <button type="button" onClick={() => setActiveTab('evolution')} className={tabClass('evolution')}>
            Evolution
          </button>
        </nav>
      </div>

      {/* Tab content */}
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
                      <th className="py-2 pr-4 text-right">Net P&amp;L</th>
                      <th className="py-2 pr-4 text-right">Avg P&amp;L</th>
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
    </div>
  );
}
