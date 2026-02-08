import { ArrowRight, TrendingDown, TrendingUp, Upload } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { getEquityCurve, getSummary } from '../api/analytics.api';
import { listTrades } from '../api/trades.api';
import { EquityCurveChart } from '../components/charts/EquityCurveChart';
import { Spinner } from '../components/ui/Spinner';
import { useAuth } from '../hooks/useAuth';
import type { AnalyticsSummary, EquityCurvePoint } from '../types/analytics.types';
import type { Trade } from '../types/trade.types';
import { formatCurrency, formatDateTime, formatPercent } from '../utils/formatters';

/** Dashboard page — overview with key stats, recent trades, and equity curve. */
export function DashboardPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [equityCurve, setEquityCurve] = useState<EquityCurvePoint[]>([]);
  const [recentTrades, setRecentTrades] = useState<Trade[]>([]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [summaryRes, equityRes, tradesRes] = await Promise.all([
          getSummary(),
          getEquityCurve(),
          listTrades({ page: 1, per_page: 5, sort_by: 'close_time', sort_dir: 'desc' }),
        ]);
        setSummary(summaryRes);
        setEquityCurve(equityRes);
        setRecentTrades(tradesRes.trades ?? tradesRes.items);
      } catch {
        // Handled by interceptor
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  if (loading) {
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
        <Upload className="w-16 h-16 text-gray-300" />
        <h1 className="text-2xl font-bold text-gray-900">Welcome to TradeLogs</h1>
        <p className="text-gray-500 text-center max-w-md">
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
    { label: 'Win Rate', value: formatPercent(summary!.win_rate * 100) },
    {
      label: 'Profit Factor',
      value: summary!.profit_factor != null ? summary!.profit_factor.toFixed(2) : '—',
    },
    {
      label: 'Expectancy',
      value: formatCurrency(summary!.expectancy),
      color: summary!.expectancy >= 0 ? 'pnl-positive' : 'pnl-negative',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <Link to="/import" className="btn-primary text-sm inline-flex items-center gap-1">
          Import <Upload className="w-4 h-4" />
        </Link>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {statCards.map((card) => (
          <div key={card.label} className="card text-center">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
              {card.label}
            </p>
            <p className={`mt-1 text-xl font-bold ${card.color ?? 'text-gray-900'}`}>
              {card.value}
            </p>
          </div>
        ))}
      </div>

      {/* Equity curve */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700">Equity Curve</h2>
          <Link to="/analytics" className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1">
            View Analytics <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
        <EquityCurveChart data={equityCurve} isLoading={false} />
      </div>

      {/* Recent trades */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700">Recent Trades</h2>
          <Link to="/trades" className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1">
            View All <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        {recentTrades.length === 0 ? (
          <p className="text-sm text-gray-400">No trades yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  <th className="py-2 pr-4">Symbol</th>
                  <th className="py-2 pr-4">Side</th>
                  <th className="py-2 pr-4">Qty</th>
                  <th className="py-2 pr-4 text-right">Net P&L</th>
                  <th className="py-2 text-right">Closed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recentTrades.map((trade) => (
                  <tr key={trade.id} className="hover:bg-gray-50">
                    <td className="py-2 pr-4">
                      <Link
                        to={`/trades/${trade.id}`}
                        className="font-medium text-blue-600 hover:underline"
                      >
                        {trade.symbol}
                      </Link>
                    </td>
                    <td className="py-2 pr-4">
                      <span className="inline-flex items-center gap-1">
                        {trade.side === 'Long' ? (
                          <TrendingUp className="w-3 h-3 text-green-500" />
                        ) : (
                          <TrendingDown className="w-3 h-3 text-red-500" />
                        )}
                        {trade.side}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-gray-600">{trade.total_quantity}</td>
                    <td
                      className={`py-2 pr-4 text-right font-medium ${
                        trade.net_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'
                      }`}
                    >
                      {formatCurrency(trade.net_pnl)}
                    </td>
                    <td className="py-2 text-right text-gray-500 text-xs">
                      {trade.exit_time ? formatDateTime(trade.exit_time, user?.display_timezone) : '—'}
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
