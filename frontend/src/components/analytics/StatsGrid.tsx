import type {
    AnalyticsSummary,
    DrawdownPoint,
} from '../../types/analytics.types';
import { formatCurrency, formatPercent } from '../../utils/formatters';
import { InfoTooltip } from '../ui/InfoTooltip';

interface StatsCardProps {
  label: string;
  value: string;
  valueColor?: string;
  tooltip?: string;
  subtitle?: string;
}

/** Single metric display card with optional info tooltip. */
function StatsCard({
  label,
  value,
  valueColor,
  tooltip,
  subtitle,
}: StatsCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-center gap-1.5">
        <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">{label}</p>
        {tooltip && <InfoTooltip text={tooltip.replace(/\\n/g, '\n')} ariaLabel={`Info about ${label}`} />}
      </div>
      <p className={`mt-1 text-lg font-bold ${valueColor ?? 'text-gray-900 dark:text-gray-100'}`}>{value}</p>
      {subtitle && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
      )}
    </div>
  );
}

function MetricSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-600 dark:text-gray-400">
        {title}
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {children}
      </div>
    </section>
  );
}

interface StatsGridProps {
  summary: AnalyticsSummary | null;
  drawdown: DrawdownPoint[];
  isLoading: boolean;
}

/** Grid of analytics metric cards. */
export function StatsGrid({
  summary,
  drawdown,
  isLoading,
}: StatsGridProps) {
  if (isLoading || !summary) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 4 }).map((_, sectionIndex) => (
          <div key={sectionIndex} className="space-y-2">
            <div className="h-3 w-40 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
              {Array.from({ length: 4 }).map((__, cardIndex) => (
                <div
                  key={cardIndex}
                  className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 animate-pulse"
                >
                  <div className="h-3 w-16 bg-gray-200 dark:bg-gray-700 rounded mb-2" />
                  <div className="h-6 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  const pnlColor = summary.total_net_pnl >= 0 ? 'text-profit' : 'text-loss';
  const feePctOfAbsGross =
    Math.abs(summary.total_gross_pnl) > 0
      ? (summary.total_fees / Math.abs(summary.total_gross_pnl)) * 100
      : 0;

  const currentDrawdown = drawdown.length > 0
    ? Math.abs(drawdown[drawdown.length - 1]!.drawdown)
    : 0;
  const maxDrawdown = drawdown.length > 0
    ? Math.abs(
      Math.min(...drawdown.map((point) => point.drawdown))
    )
    : 0;

  const netProfitFactor = (() => {
    if (summary.profit_factor != null) {
      return summary.profit_factor.toFixed(2);
    }
    if (summary.winners > 0 && summary.losers === 0) {
      return '∞';
    }
    return 'N/A';
  })();

  const profitFactorR = (() => {
    if (summary.profit_factor_r != null) {
      return summary.profit_factor_r.toFixed(2);
    }
    return 'N/A';
  })();

  return (
    <div className="space-y-5">
      <MetricSection title="Results">
        <StatsCard
          label="Total Trades"
          value={String(summary.total_trades)}
        />

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 sm:col-span-2 xl:col-span-2">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-1.5">
                <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Cumulated Net P&amp;L
                </p>
                <InfoTooltip
                  text={
                    'Sum of net P&L across all closed trades after fees.\n'
                    + 'Also shows total fees and fees as a % of |gross P&L|.\n'
                    + 'Breakeven = trades with gross P&L = 0.'
                  }
                  ariaLabel="Info about Cumulated Net P&L"
                />
              </div>
              <p className={`mt-1 text-lg font-bold ${pnlColor}`}>
                {formatCurrency(summary.total_net_pnl)}
              </p>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Fees: {formatCurrency(summary.total_fees)}
                {' '}({formatPercent(feePctOfAbsGross, 1)} of |Gross|)
              </p>
            </div>

            <div className="text-right text-xs text-gray-500 dark:text-gray-400">
              <p>Winners: <span className="font-semibold text-gray-700 dark:text-gray-300">{summary.winners}</span></p>
              <p>Breakeven: <span className="font-semibold text-gray-700 dark:text-gray-300">{summary.breakeven}</span></p>
              <p>Losers: <span className="font-semibold text-gray-700 dark:text-gray-300">{summary.losers}</span></p>
            </div>
          </div>
        </div>

        <StatsCard
          label="Win Rate"
          value={formatPercent(summary.win_rate)}
          tooltip="Percentage of trades that were winners (net P&L > 0).\nFormula: Winners ÷ Total Trades × 100"
        />
        <StatsCard
          label="APPT"
          value={formatCurrency(summary.appt)}
          valueColor={summary.appt >= 0 ? 'text-profit' : 'text-loss'}
          tooltip="Average Profitability Per Trade.\nFormula: Total Net P&L ÷ Total Trades"
        />
        <StatsCard
          label="Net Profit Factor ($)"
          value={netProfitFactor}
          valueColor={
            summary.profit_factor != null && summary.profit_factor >= 1
              ? 'text-profit'
              : 'text-loss'
          }
          tooltip="Ratio of total winning P&L to total losing P&L (dollar-based).\nFormula: Σ(winner net P&L) ÷ |Σ(loser net P&L)|"
        />
      </MetricSection>

      <MetricSection title="Edge (risk-normalized)">
        <StatsCard
          label="Expectancy (R)"
          value={summary.expectancy_r != null ? `${summary.expectancy_r.toFixed(2)}R` : 'N/A'}
          valueColor={summary.expectancy_r != null && summary.expectancy_r >= 0 ? 'text-profit' : 'text-loss'}
          tooltip="Expected value per trade in R-multiples.\nFormula: p(win) × avg(win R) − p(loss) × |avg(loss R)|"
        />
        <StatsCard
          label="W:L Ratio (R)"
          value={summary.wl_ratio_r != null ? summary.wl_ratio_r.toFixed(2) : 'N/A'}
          valueColor={summary.wl_ratio_r != null && summary.wl_ratio_r >= 1 ? 'text-profit' : 'text-loss'}
          tooltip="Average winning R divided by average losing R.\nFormula: avg(win R) ÷ |avg(loss R)|"
        />
        <StatsCard
          label="Profit Factor (R)"
          value={profitFactorR}
          valueColor={summary.profit_factor_r != null && summary.profit_factor_r >= 1 ? 'text-profit' : 'text-loss'}
          tooltip="Ratio of total positive R to total negative R.\nFormula: Σ(positive R) ÷ |Σ(negative R)|"
        />
        <StatsCard
          label="Median R"
          value={summary.median_r != null ? `${summary.median_r.toFixed(2)}R` : 'N/A'}
          valueColor={summary.median_r != null && summary.median_r >= 0 ? 'text-profit' : 'text-loss'}
          tooltip="50th percentile of trade R-multiples.\nOnly trades with initial risk > 0 are included."
        />
      </MetricSection>

      <MetricSection title="Risk">
        <StatsCard
          label="Current Drawdown ($)"
          value={formatCurrency(currentDrawdown)}
          valueColor={currentDrawdown > 0 ? 'text-loss' : undefined}
          tooltip="Current peak-to-trough decline in the equity curve.\nMeasured from the most recent equity peak."
        />
        <StatsCard
          label="Max Drawdown ($)"
          value={formatCurrency(maxDrawdown)}
          valueColor={maxDrawdown > 0 ? 'text-loss' : undefined}
          tooltip="Largest peak-to-trough decline observed across the entire equity curve."
        />
        <StatsCard
          label="Avg Initial Risk (No Fees) ($)"
          value={formatCurrency(summary.avg_initial_risk)}
          tooltip="Average initial risk per trade.\nOnly trades with initial risk > 0 are included."
        />
      </MetricSection>

      <MetricSection title="Sizing / per-share">
        <StatsCard
          label="Win / Share Avg"
          value={formatCurrency(summary.win_per_share_avg)}
          valueColor="text-profit"
          tooltip="Average net P&L per contract among winning trades.\nFormula: Σ(winner net P&L ÷ qty) ÷ Winners"
        />
        <StatsCard
          label="Loss / Share Avg"
          value={formatCurrency(summary.loss_per_share_avg)}
          valueColor="text-loss"
          tooltip="Average net P&L per contract among losing trades.\nFormula: Σ(loser net P&L ÷ qty) ÷ Losers"
        />
        <StatsCard
          label="Win / Share P95"
          value={formatCurrency(summary.win_per_share_p95)}
          valueColor="text-profit"
          tooltip={
            '95th percentile of winner P&L per contract.\n'
            + 'Represents near-best performance without outlier dominance.\n'
            + 'Formula: P95(net_pnl ÷ qty for winners)'
          }
        />
        <StatsCard
          label="Loss / Share P05"
          value={formatCurrency(summary.loss_per_share_p05)}
          valueColor="text-loss"
          tooltip={
            '5th percentile of loser P&L per contract.\n'
            + 'Represents near-worst performance without outlier dominance.\n'
            + 'Formula: P05(net_pnl ÷ qty for losers)'
          }
        />

        {/*
        <StatsCard
          label="Win / Share High"
          value={formatCurrency(summary.win_per_share_high)}
          valueColor="text-profit"
          tooltip="Best net P&L per contract among winning trades. max(winner P&L ÷ qty)."
        />
        <StatsCard
          label="Loss / Share High"
          value={formatCurrency(summary.loss_per_share_high)}
          valueColor="text-loss"
          tooltip="Worst net P&L per contract among losing trades. min(loser P&L ÷ qty)."
        />
        */}
      </MetricSection>
    </div>
  );
}
