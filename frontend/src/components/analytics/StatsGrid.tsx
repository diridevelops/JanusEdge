import type { AnalyticsSummary } from '../../types/analytics.types';
import { formatCurrency, formatDuration, formatPercent } from '../../utils/formatters';

interface StatsCardProps {
  label: string;
  value: string;
  valueColor?: string;
}

/** Single metric display card. */
function StatsCard({ label, value, valueColor }: StatsCardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className={`mt-1 text-lg font-bold ${valueColor ?? 'text-gray-900'}`}>{value}</p>
    </div>
  );
}

interface StatsGridProps {
  summary: AnalyticsSummary | null;
  isLoading: boolean;
}

/** Grid of analytics metric cards. */
export function StatsGrid({ summary, isLoading }: StatsGridProps) {
  if (isLoading || !summary) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="bg-white border border-gray-200 rounded-lg p-4 animate-pulse">
            <div className="h-3 w-16 bg-gray-200 rounded mb-2" />
            <div className="h-6 w-20 bg-gray-200 rounded" />
          </div>
        ))}
      </div>
    );
  }

  const pnlColor = summary.total_net_pnl >= 0 ? 'text-profit' : 'text-loss';

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      <StatsCard label="Total Trades" value={String(summary.total_trades)} />
      <StatsCard
        label="Win Rate"
        value={formatPercent(summary.win_rate)}
        valueColor={summary.win_rate >= 0.5 ? 'text-profit' : 'text-loss'}
      />
      <StatsCard
        label="Net P&L"
        value={formatCurrency(summary.total_net_pnl)}
        valueColor={pnlColor}
      />
      <StatsCard
        label="Profit Factor"
        value={summary.profit_factor != null ? summary.profit_factor.toFixed(2) : 'N/A'}
        valueColor={
          summary.profit_factor != null && summary.profit_factor >= 1 ? 'text-profit' : 'text-loss'
        }
      />
      <StatsCard
        label="Expectancy"
        value={formatCurrency(summary.expectancy)}
        valueColor={summary.expectancy >= 0 ? 'text-profit' : 'text-loss'}
      />
      <StatsCard
        label="Avg Winner"
        value={formatCurrency(summary.avg_winner)}
        valueColor="text-profit"
      />
      <StatsCard
        label="Avg Loser"
        value={formatCurrency(summary.avg_loser)}
        valueColor="text-loss"
      />
      <StatsCard
        label="Largest Win"
        value={formatCurrency(summary.largest_win)}
        valueColor="text-profit"
      />
      <StatsCard
        label="Largest Loss"
        value={formatCurrency(summary.largest_loss)}
        valueColor="text-loss"
      />
      <StatsCard
        label="Avg Duration"
        value={formatDuration(summary.avg_holding_time_seconds)}
      />
    </div>
  );
}
