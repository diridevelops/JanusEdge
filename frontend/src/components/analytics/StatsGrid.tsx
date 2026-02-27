import { Info } from 'lucide-react';
import { useRef, useState } from 'react';
import type { AnalyticsSummary } from '../../types/analytics.types';
import { formatCurrency, formatPercent } from '../../utils/formatters';

interface StatsCardProps {
  label: string;
  value: string;
  valueColor?: string;
  tooltip?: string;
}

/** Single metric display card with optional info tooltip. */
function StatsCard({ label, value, valueColor, tooltip }: StatsCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const btnRef = useRef<HTMLButtonElement | null>(null);

  function openTooltip() {
    const rect = btnRef.current?.getBoundingClientRect();
    if (rect) {
      const tipW = 224; // w-56 = 14rem = 224px
      let left = rect.left + rect.width / 2;
      // Clamp so the tooltip doesn't overflow viewport edges
      left = Math.max(tipW / 2 + 8, Math.min(left, globalThis.innerWidth - tipW / 2 - 8));
      setPos({ top: rect.top - 8, left });
    }
    setShowTooltip(true);
  }

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-center gap-1.5">
        <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">{label}</p>
        {tooltip && (
          <button
            ref={btnRef}
            type="button"
            className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors"
            onMouseEnter={openTooltip}
            onMouseLeave={() => setShowTooltip(false)}
            onFocus={openTooltip}
            onBlur={() => setShowTooltip(false)}
            aria-label={`Info about ${label}`}
          >
            <Info className="w-3.5 h-3.5" strokeWidth={2.25} />
          </button>
        )}
      </div>
      <p className={`mt-1 text-lg font-bold ${valueColor ?? 'text-gray-900 dark:text-gray-100'}`}>{value}</p>
      {tooltip && showTooltip && (
        <div
          className="fixed z-[120] w-56 px-3 py-2 text-xs text-gray-100 bg-gray-800 dark:bg-gray-700 rounded-lg shadow-lg whitespace-pre-line pointer-events-none"
          style={{ top: pos.top, left: pos.left, transform: 'translate(-50%, -100%)' }}
        >
          {tooltip.replace(/\\n/g, '\n')}
          <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-x-4 border-x-transparent border-t-4 border-t-gray-800 dark:border-t-gray-700" />
        </div>
      )}
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
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 animate-pulse">
            <div className="h-3 w-16 bg-gray-200 dark:bg-gray-700 rounded mb-2" />
            <div className="h-6 w-20 bg-gray-200 dark:bg-gray-700 rounded" />
          </div>
        ))}
      </div>
    );
  }

  const pnlColor = summary.total_net_pnl >= 0 ? 'text-profit' : 'text-loss';

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <StatsCard
        label="Cumulated Net P&L"
        value={formatCurrency(summary.total_net_pnl)}
        valueColor={pnlColor}
        tooltip="Sum of net P&L across all closed trades after fees."
      />
      <StatsCard
        label="Win Rate"
        value={formatPercent(summary.win_rate)}
        valueColor={summary.win_rate >= 50 ? 'text-profit' : 'text-loss'}
        tooltip="Winners ÷ Total Trades × 100"
      />
      <StatsCard
        label="APPT"
        value={formatCurrency(summary.appt)}
        valueColor={summary.appt >= 0 ? 'text-profit' : 'text-loss'}
        tooltip="Average Profitability Per Trade\nTotal Net P&L ÷ Total Trades"
      />
      <StatsCard
        label="W:L Ratio (R)"
        value={summary.wl_ratio_r != null ? summary.wl_ratio_r.toFixed(2) : 'N/A'}
        valueColor={
          summary.wl_ratio_r != null && summary.wl_ratio_r >= 1 ? 'text-profit' : 'text-loss'
        }
        tooltip="Avg Win R-multiple ÷ |Avg Loss R-multiple|\nComputed only on trades with defined initial risk"
      />
      <StatsCard
        label="P/L Ratio"
        value={summary.pl_ratio != null ? summary.pl_ratio.toFixed(2) : 'N/A'}
        valueColor={
          summary.pl_ratio != null && summary.pl_ratio >= 1 ? 'text-profit' : 'text-loss'
        }
        tooltip="Average win ($) ÷ |Average loss ($)|"
      />
      <StatsCard
        label="Expectancy (R)"
        value={summary.expectancy_r != null ? `${summary.expectancy_r.toFixed(2)}R` : 'N/A'}
        valueColor={
          summary.expectancy_r != null && summary.expectancy_r >= 0
            ? 'text-profit'
            : 'text-loss'
        }
        tooltip="Average R-multiple per trade\nComputed only on trades with defined initial risk\nFormula: Win Rate × Avg Win R − (1 − Win Rate) × Avg Loss R"
      />
      <StatsCard
        label="Win / Share Avg"
        value={formatCurrency(summary.win_per_share_avg)}
        valueColor="text-profit"
        tooltip="Average net P&L per contract for winning trades.\nΣ(winner P&L ÷ qty) ÷ # winners"
      />
      <StatsCard
        label="Loss / Share Avg"
        value={formatCurrency(summary.loss_per_share_avg)}
        valueColor="text-loss"
        tooltip="Average net P&L per contract for losing trades.\nΣ(loser P&L ÷ qty) ÷ # losers"
      />
      <StatsCard
        label="Win / Share High"
        value={formatCurrency(summary.win_per_share_high)}
        valueColor="text-profit"
        tooltip="Best net P&L per contract among winning trades.\nmax(winner P&L ÷ qty)"
      />
      <StatsCard
        label="Loss / Share High"
        value={formatCurrency(summary.loss_per_share_high)}
        valueColor="text-loss"
        tooltip="Worst net P&L per contract among losing trades.\nmin(loser P&L ÷ qty)"
      />
    </div>
  );
}
