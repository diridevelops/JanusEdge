import { ChevronDown, ChevronRight, FlaskConical, Loader2 } from 'lucide-react';
import { startTransition, useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { getSummary } from '../api/analytics.api';
import { getStopAnalysis, getWickedOutTrades, runSimulation } from '../api/whatif.api';
import { MonteCarloSimulator } from '../components/analytics/MonteCarloSimulator';
import { FilterBar } from '../components/filters/FilterBar';
import { InfoTooltip } from '../components/ui/InfoTooltip';
import { PageHeader } from '../components/ui/PageHeader';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import type { AnalyticsSummary } from '../types/analytics.types';
import type {
  ConfidenceInterval,
  SimulationDetail,
  SimulationResponse,
  StopAnalysisResponse,
  WickedOutTrade,
} from '../types/whatif.types';
import { formatCurrency, formatPnL } from '../utils/formatters';

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function MetricCard({
  label,
  value,
  descriptionTooltip,
  ciTooltip,
}: {
  label: string;
  value: string;
  descriptionTooltip?: string;
  ciTooltip?: string;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap flex items-center gap-1">
        {label}
        {descriptionTooltip ? (
          <InfoTooltip text={descriptionTooltip} ariaLabel={`Info about ${label}`} iconSize="w-3 h-3" />
        ) : null}
      </span>
      <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-1">
        {value}
        {ciTooltip ? (
          <InfoTooltip
            text={ciTooltip}
            ariaLabel={`Confidence interval for ${label}`}
            iconSize="w-2.5 h-2.5"
            widthClass="w-72"
            iconVariant="question"
          />
        ) : null}
      </span>
    </div>
  );
}

function formatBcaTooltip(ci: ConfidenceInterval | null | undefined) {
  if (!ci) return undefined;
  return `95% bootstrap CI: [${ci.lower.toFixed(2)}, ${ci.upper.toFixed(2)}]`;
}

function getStopMetricTooltip(label: string) {
  switch (label) {
    case 'Mean':
      return 'Average overshoot in R-multiples across all wicked-out trades.';
    case 'Median':
      return 'Middle overshoot value when all overshoots are sorted. If you widen the stop by this amount, about 50% of wicked-out trades would be expected to become winners.';
    case 'P75':
      return '75th percentile of overshoot in R. If you widen the stop by this amount, about 75% of wicked-out trades would be expected to become winners.';
    case 'P90':
      return '90th percentile of overshoot in R. If you widen the stop by this amount, about 90% of wicked-out trades would be expected to become winners.';
    case 'P95':
      return '95th percentile of overshoot in R. If you widen the stop by this amount, about 95% of wicked-out trades would be expected to become winners.';
    case 'IQR':
      return 'Spread of the middle 50% of overshoots.\nFormula: P75(overshoot_R) - P25(overshoot_R)';
    default:
      return undefined;
  }
}

function DeltaCell({
  value,
  isCurrency = false,
  suffix = '',
  decimals = 2,
  favorableWhenNegative = false,
}: {
  value: number | null;
  isCurrency?: boolean;
  suffix?: string;
  decimals?: number;
  favorableWhenNegative?: boolean;
}) {
  if (value == null) {
    return <span className="text-gray-500">—</span>;
  }

  const positive = value > 0;
  const negative = value < 0;
  const cls = positive
    ? favorableWhenNegative
      ? 'pnl-negative'
      : 'pnl-positive'
    : negative
      ? favorableWhenNegative
        ? 'pnl-positive'
        : 'pnl-negative'
      : 'text-gray-500';
  let text: string;

  if (!Number.isFinite(value)) {
    text = value > 0 ? '+Inf' : value < 0 ? '-Inf' : '0.00';
  } else {
    text = isCurrency
      ? `${positive ? '+' : ''}${formatCurrency(value)}`
      : `${positive ? '+' : ''}${value.toFixed(decimals)}${suffix}`;
  }

  return <span className={cls}>{text}</span>;
}

function formatRValue(value: number | null) {
  return value == null ? '—' : `${value.toFixed(2)}R`;
}

function CardLoadingOverlay({ label }: { label: string }) {
  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/70 dark:bg-gray-900/70">
      <div className="flex items-center gap-2 rounded-md border border-gray-200 bg-white/90 px-3 py-2 text-xs text-gray-600 shadow-sm dark:border-gray-700 dark:bg-gray-800/90 dark:text-gray-300">
        <Loader2 className="h-4 w-4 animate-spin text-brand-600" />
        <span>{label}</span>
      </div>
    </div>
  );
}

function parseProfitFactor(value: number | string): number | null {
  if (typeof value === 'number') {
    return value;
  }
  if (value === 'Inf') {
    return Number.POSITIVE_INFINITY;
  }
  return null;
}

function buildSimulationViewModel(response: SimulationResponse) {
  const originalProfitFactor = parseProfitFactor(response.original.profit_factor);
  const whatIfProfitFactor = parseProfitFactor(response.what_if.profit_factor);
  const profitFactorDelta =
    originalProfitFactor === null || whatIfProfitFactor === null
      ? null
      : Number.isFinite(originalProfitFactor) && Number.isFinite(whatIfProfitFactor)
        ? whatIfProfitFactor - originalProfitFactor
        : originalProfitFactor === whatIfProfitFactor
          ? 0
          : whatIfProfitFactor - originalProfitFactor;

  const convertedDetails = response.details.filter((detail) => detail.converted);
  const simulatedDetails = response.details.filter(
    (detail) => detail.status === 'simulated' && !detail.converted,
  );
  const skippedDetails = response.details.filter(
    (detail) => detail.status !== 'simulated' && !detail.converted,
  );

  return {
    original: response.original,
    whatIf: response.what_if,
    delta: {
      total_pnl: response.what_if.total_pnl - response.original.total_pnl,
      avg_pnl: response.what_if.avg_pnl - response.original.avg_pnl,
      win_rate: response.what_if.win_rate - response.original.win_rate,
      expectancy_r:
        response.original.expectancy_r !== null && response.what_if.expectancy_r !== null
          ? response.what_if.expectancy_r - response.original.expectancy_r
          : null,
      winners_change: response.what_if.total_winners - response.original.total_winners,
      losers_change: response.what_if.total_losers - response.original.total_losers,
      profit_factor: profitFactorDelta,
    },
    tradesTotal: response.trades_total,
    tradesConverted: response.trades_converted,
    tradesSimulated: response.trades_simulated,
    tradesSkipped: response.trades_skipped,
    convertedDetails,
    simulatedDetails,
    skippedDetails,
  };
}

function getAnalysisConfidenceInterval(
  analysis: StopAnalysisResponse | null,
  metric: 'mean' | 'median' | 'p75' | 'p90' | 'p95' | 'iqr',
): ConfidenceInterval | null {
  if (!analysis) {
    return null;
  }

  return analysis.confidence_intervals?.[metric] ?? null;
}

function getSimulationStatusLabel(detail: SimulationDetail) {
  const targetSourceSuffix = detail.target_source
    ? `: ${detail.target_source} target`
    : '';

  switch (detail.status) {
    case 'no_target':
      return 'Skipped: no target';
    case 'no_data':
      return `Skipped: no market data${targetSourceSuffix}`;
    case 'no_target_risk':
      return 'Skipped: no target and no risk';
    case 'no_risk':
      return 'Skipped: no risk';
    case 'simulated':
      return `Simulated${targetSourceSuffix}`;
    case 'winner':
      return 'Winner: nothing to do';
    default:
      return detail.status;
  }
}

function getConvertedStatusLabel(detail: SimulationDetail) {
  if (!detail.target_source) {
    return 'Converted to winner';
  }
  return `Converted to winner: ${detail.target_source} target`;
}

function ResultSection({
  title,
  count,
  expanded,
  onToggle,
  trades,
}: {
  title: string;
  count: number;
  expanded: boolean;
  onToggle: () => void;
  trades: SimulationDetail[];
}) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400" />
          )}
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{title}</span>
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400">{count}</span>
      </button>

      {expanded && (
        <div className="border-t border-gray-200 dark:border-gray-700">
          {trades.length === 0 ? (
            <p className="px-4 py-4 text-sm text-gray-400 dark:text-gray-500">No trades in this section.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[920px] table-fixed text-sm">
                <colgroup>
                  <col className="w-[12%]" />
                  <col className="w-[12%]" />
                  <col className="w-[10%]" />
                  <col className="w-[12%]" />
                  <col className="w-[12%]" />
                  <col className="w-[12%]" />
                  <col className="w-[12%]" />
                  <col className="w-[18%]" />
                </colgroup>
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    <th className="px-4 py-2 text-left">Trade</th>
                    <th className="px-4 py-2 text-left">Date</th>
                    <th className="px-4 py-2 text-left">Side</th>
                    <th className="px-4 py-2 text-left">Original P&L</th>
                    <th className="px-4 py-2 text-left">New P&L</th>
                    <th className="px-4 py-2 text-left">Change P&amp;L</th>
                    <th className="px-4 py-2 text-left">Change R</th>
                    <th className="px-4 py-2 text-left">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade) => {
                    const original = formatPnL(trade.original_pnl);
                    const next = formatPnL(trade.new_pnl);
                    return (
                      <tr
                        key={`${title}-${trade.trade_id}`}
                        className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30"
                      >
                        <td className="px-4 py-2">
                          <Link
                            to={`/trades/${trade.trade_id}`}
                            className="block truncate text-brand-600 hover:underline"
                          >
                            {trade.symbol} · {trade.trade_id.slice(-6)}
                          </Link>
                        </td>
                        <td className="px-4 py-2 text-gray-600 dark:text-gray-300">
                          {new Date(trade.entry_time).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">{trade.side}</td>
                        <td className={`px-4 py-2 text-left ${original.className}`}>{original.text}</td>
                        <td className={`px-4 py-2 text-left ${next.className}`}>{next.text}</td>
                        <td className="px-4 py-2 text-left">
                          <DeltaCell value={trade.new_pnl - trade.original_pnl} isCurrency />
                        </td>
                        <td className="px-4 py-2 text-left">
                          <DeltaCell value={trade.change_r} suffix="R" />
                        </td>
                        <td className="px-4 py-2 text-gray-600 dark:text-gray-300">
                          {trade.converted
                            ? getConvertedStatusLabel(trade)
                            : getSimulationStatusLabel(trade)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

type WhatIfTab = 'simulator' | 'stop-management';
type WhatIfReplayMode = 'ohlc' | 'tick';

/** What-if page: stop analysis, wicked-out trades, and simulation. */
export function WhatIfPage() {
  const { user } = useAuth();
  const { addToast } = useToast();
  const [activeTab, setActiveTab] = useState<WhatIfTab>('simulator');

  // Filters
  const [filters, setFilters] = useState({
    symbol: '',
    side: '',
    account: '',
    tag: '',
    date_from: '',
    date_to: '',
  });

  function handleFilterChange(key: string, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }
  function handleClearFilters() {
    setFilters({ symbol: '', side: '', account: '', tag: '', date_from: '', date_to: '' });
  }

  const apiFilters = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== ''),
  ) as Record<string, string>;

  // ---- Filtered summary ----
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const summaryRequestIdRef = useRef(0);

  // ---- Stop Analysis ----
  const [analysis, setAnalysis] = useState<StopAnalysisResponse | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);

  // ---- Wicked-out trades ----
  const [woTrades, setWoTrades] = useState<WickedOutTrade[]>([]);
  const [woExpanded, setWoExpanded] = useState(false);
  const [woLoading, setWoLoading] = useState(false);

  // ---- Simulation ----
  const [rWidening, setRWidening] = useState('0.5');
  const [replayMode, setReplayMode] = useState<WhatIfReplayMode>('ohlc');
  const [simLoading, setSimLoading] = useState(false);
  const [simResult, setSimResult] = useState<ReturnType<typeof buildSimulationViewModel> | null>(null);
  const [resultSectionsExpanded, setResultSectionsExpanded] = useState({
    converted: true,
    simulated: false,
    skipped: false,
  });
  const simCache = useRef<Map<string, ReturnType<typeof buildSimulationViewModel>>>(new Map());
  const dataRequestIdRef = useRef(0);
  const simulationRequestIdRef = useRef(0);
  const whatIfTargetRMultiple = user?.whatif_target_r_multiple ?? 2;

  const fetchSummary = useCallback(async (f: Record<string, string>) => {
    const requestId = summaryRequestIdRef.current + 1;
    summaryRequestIdRef.current = requestId;
    setSummaryLoading(true);
    try {
      const summaryRes = await getSummary(f);
      if (requestId !== summaryRequestIdRef.current) {
        return;
      }
      setSummary(summaryRes);
    } catch {
      // Silenced — 401 handled by interceptor
    } finally {
      if (requestId === summaryRequestIdRef.current) {
        setSummaryLoading(false);
      }
    }
  }, []);

  // Fetch analysis + wicked-out trades on filter change
  const fetchData = useCallback(async (f: Record<string, string>) => {
    const requestId = dataRequestIdRef.current + 1;
    dataRequestIdRef.current = requestId;
    setAnalysisLoading(true);
    setWoLoading(true);
    try {
      const [analysisRes, woRes] = await Promise.all([
        getStopAnalysis(f),
        getWickedOutTrades(f),
      ]);
      if (requestId !== dataRequestIdRef.current) {
        return;
      }
      setAnalysis(analysisRes);
      setWoTrades(woRes.trades);
    } catch {
      // Silenced — 401 handled by interceptor
    } finally {
      if (requestId === dataRequestIdRef.current) {
        setAnalysisLoading(false);
        setWoLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void fetchData(apiFilters);
    // Reset simulation results on filter change
    setSimResult(null);
    simCache.current.clear();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.symbol, filters.side, filters.account, filters.tag, filters.date_from, filters.date_to]);

  useEffect(() => {
    void fetchSummary(apiFilters);
  }, [fetchSummary, filters.symbol, filters.side, filters.account, filters.tag, filters.date_from, filters.date_to]);

  useEffect(() => {
    setSimResult(null);
  }, [replayMode, whatIfTargetRMultiple]);

  // Simulation handler
  async function handleSimulate() {
    const rVal = parseFloat(rWidening);
    if (isNaN(rVal) || rVal <= 0 || rVal > 10) {
      addToast('error', 'R-widening must be between 0.1 and 10');
      return;
    }

    const cacheKey = `${rVal}_${replayMode}_${whatIfTargetRMultiple}_${JSON.stringify(apiFilters)}`;
    const cached = simCache.current.get(cacheKey);
    if (cached) {
      setSimResult(cached);
      return;
    }

    const requestId = simulationRequestIdRef.current + 1;
    simulationRequestIdRef.current = requestId;
    setSimLoading(true);
    try {
      const response = await runSimulation(rVal, replayMode, apiFilters);
      if (requestId !== simulationRequestIdRef.current) {
        return;
      }
      const viewModel = buildSimulationViewModel(response);
      startTransition(() => {
        setSimResult(viewModel);
        setResultSectionsExpanded({
          converted: true,
          simulated: false,
          skipped: false,
        });
        simCache.current.set(cacheKey, viewModel);
        setSimLoading(false);
      });
    } catch {
      addToast('error', 'Simulation failed');
      if (requestId === simulationRequestIdRef.current) {
        setSimLoading(false);
      }
    }
  }

  // Wicked-out summary counts
  const woWithData = woTrades.filter((t) => t.has_tick_data).length;
  const woMissing = woTrades.length - woWithData;
  const overshootByTradeId = new Map(
    (analysis?.details ?? []).map((detail) => [detail.trade_id, detail.overshoot_r]),
  );
  const tabClass = (tab: WhatIfTab) =>
    `px-4 py-2 text-sm font-medium rounded-t-md border border-b-0 ${
      activeTab === tab
        ? 'bg-white text-gray-900 border-gray-300 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-600'
        : 'bg-gray-100 text-gray-600 border-transparent hover:text-gray-800 dark:bg-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
    }`;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <PageHeader
        icon={FlaskConical}
        title="What-if"
        description="Run wider-stop simulations or inspect stop-management analysis. Trades without a saved target use your Settings default target R-multiple when original risk is available."
      />

      {/* Filters */}
      <FilterBar
        filters={filters}
        onFilterChange={handleFilterChange}
        onClearFilters={handleClearFilters}
      />

      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-2" aria-label="What-if tabs">
          <button
            type="button"
            onClick={() => startTransition(() => setActiveTab('simulator'))}
            className={tabClass('simulator')}
          >
            Simulator
          </button>
          <button
            type="button"
            onClick={() => startTransition(() => setActiveTab('stop-management'))}
            className={tabClass('stop-management')}
          >
            Stop management
          </button>
        </nav>
      </div>

      {activeTab === 'simulator' ? (
        summaryLoading && !summary ? (
          <div className="card p-8 text-center text-gray-500 dark:text-gray-400">
            <div className="flex items-center justify-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin text-brand-600" />
              <span>Loading filtered trade metrics…</span>
            </div>
          </div>
        ) : (
          <MonteCarloSimulator summary={summary} summaryLoading={summaryLoading} filters={filters} />
        )
      ) : (
        <>
          {/* ---- Wicked-Out Trades ---- */}
          <div className="card relative overflow-hidden">
            {woLoading && woTrades.length > 0 ? <CardLoadingOverlay label="Updating wicked-out trades…" /> : null}
            <button
              type="button"
              onClick={() => setWoExpanded((p) => !p)}
              className="w-full flex items-center justify-between px-6 py-4 text-left"
            >
              <div className="flex items-center gap-2">
                {woExpanded ? (
                  <ChevronDown className="h-4 w-4 text-gray-400" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-gray-400" />
                )}
                <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
                  Wicked-Out Trades
                </h2>
              </div>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {woLoading ? (
                  'Loading…'
                ) : (
                  `${woTrades.length} trade${woTrades.length !== 1 ? 's' : ''} (${woWithData} with tick data, ${woMissing} missing tick data)`
                )}
              </span>
            </button>

            {woExpanded && (
              <div className="border-t border-gray-200 dark:border-gray-700">
                {woLoading ? (
                  <div className="flex justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
                  </div>
                ) : woTrades.length === 0 ? (
                  <p className="px-6 py-8 text-center text-sm text-gray-400 dark:text-gray-500">
                    No wicked-out trades found for the current filters.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                          <th className="px-4 py-2 text-left">Symbol</th>
                          <th className="px-4 py-2 text-left">Date</th>
                          <th className="px-4 py-2 text-left">Side</th>
                          <th className="px-4 py-2 text-right">Net P&L</th>
                          <th className="px-4 py-2 text-right">Wishful Stop</th>
                          <th className="px-4 py-2 text-right">Target</th>
                          <th className="px-4 py-2 text-right">Overshoot</th>
                          <th className="px-4 py-2 text-center">Tick Data</th>
                        </tr>
                      </thead>
                      <tbody>
                        {woTrades.map((t) => {
                          const pnl = formatPnL(t.net_pnl);
                          const overshoot = overshootByTradeId.get(t.id);
                          return (
                            <tr
                              key={t.id}
                              className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30"
                            >
                              <td className="px-4 py-2">
                                <Link
                                  to={`/trades/${t.id}`}
                                  className="text-brand-600 hover:underline"
                                >
                                  {t.symbol}
                                </Link>
                              </td>
                              <td className="px-4 py-2 text-gray-600 dark:text-gray-300">
                                {new Date(t.entry_time).toLocaleDateString()}
                              </td>
                              <td className="px-4 py-2">
                                <span
                                  className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                                    t.side === 'Long'
                                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                      : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                  }`}
                                >
                                  {t.side}
                                </span>
                              </td>
                              <td className={`px-4 py-2 text-right ${pnl.className}`}>{pnl.text}</td>
                              <td className="px-4 py-2 text-right text-gray-700 dark:text-gray-300">
                                {t.wish_stop_price != null ? t.wish_stop_price.toFixed(2) : '—'}
                              </td>
                              <td className="px-4 py-2 text-right text-gray-700 dark:text-gray-300">
                                {t.target_price != null ? t.target_price.toFixed(2) : '—'}
                              </td>
                              <td className="px-4 py-2 text-right text-gray-700 dark:text-gray-300">
                                {overshoot != null ? `${overshoot.toFixed(2)}R` : '—'}
                              </td>
                              <td className="px-4 py-2 text-center">
                                {t.has_tick_data ? (
                                  <span className="text-green-600 dark:text-green-400" title="Market data available">✓</span>
                                ) : (
                                  <span className="text-amber-500 dark:text-amber-400" title="Missing market data">⚠</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ---- Stop Management ---- */}
          <div className="card relative p-6">
            {analysisLoading && analysis ? <CardLoadingOverlay label="Updating stop analysis…" /> : null}
            <div className="flex items-center gap-1 mb-4">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
                Overshoot in R
              </h2>
              <InfoTooltip
                text={
                  'How far past your stop the price went before reversing.\n' +
                  'overshoot_R = |exit_price − wish_stop| / |entry_price − exit_price|\n' +
                  'Multiply it by your initial risk to determine the dollar amount by which your stop-loss should increase.\n' +
                  'Lower values mean your stop was closer to optimal.'
                }
                widthClass="w-80"
              />
            </div>

            {analysisLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
              </div>
            ) : !analysis || analysis.count === 0 ? (
              <p className="text-sm text-gray-400 dark:text-gray-500">
                No wicked-out trades with wishful stop data for the current filters.
              </p>
            ) : (
              <>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                  Based on {analysis.count} wicked-out trade{analysis.count !== 1 ? 's' : ''}
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                  <MetricCard
                    label="Mean"
                    value={`${analysis.mean.toFixed(2)}R`}
                    descriptionTooltip={getStopMetricTooltip('Mean')}
                    ciTooltip={formatBcaTooltip(getAnalysisConfidenceInterval(analysis, 'mean'))}
                  />
                  <MetricCard
                    label="Median"
                    value={`${analysis.median.toFixed(2)}R`}
                    descriptionTooltip={getStopMetricTooltip('Median')}
                    ciTooltip={formatBcaTooltip(getAnalysisConfidenceInterval(analysis, 'median'))}
                  />
                  <MetricCard
                    label="P75"
                    value={`${analysis.p75.toFixed(2)}R`}
                    descriptionTooltip={getStopMetricTooltip('P75')}
                    ciTooltip={formatBcaTooltip(getAnalysisConfidenceInterval(analysis, 'p75'))}
                  />
                  <MetricCard
                    label="P90"
                    value={`${analysis.p90.toFixed(2)}R`}
                    descriptionTooltip={getStopMetricTooltip('P90')}
                    ciTooltip={formatBcaTooltip(getAnalysisConfidenceInterval(analysis, 'p90'))}
                  />
                  <MetricCard
                    label="P95"
                    value={`${analysis.p95.toFixed(2)}R`}
                    descriptionTooltip={getStopMetricTooltip('P95')}
                    ciTooltip={formatBcaTooltip(getAnalysisConfidenceInterval(analysis, 'p95'))}
                  />
                  <MetricCard
                    label="IQR"
                    value={`${analysis.iqr.toFixed(2)}R`}
                    descriptionTooltip={getStopMetricTooltip('IQR')}
                    ciTooltip={formatBcaTooltip(getAnalysisConfidenceInterval(analysis, 'iqr'))}
                  />
                </div>
              </>
            )}
          </div>

          {/* ---- What-If Calculator ---- */}
          <div className="card p-6">
            <div className="flex items-center gap-1 mb-4">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
                What-If Calculator
              </h2>
              <InfoTooltip
                text={
                  'Simulate widening your stop across all trades:\n' +
                  '- Winners keep their P&L.\n' +
                  '- Losing trades with a saved target use that explicit target.\n' +
                  `- Losing trades without a target derive one from original risk using your Settings default (${whatIfTargetRMultiple}R).\n` +
                  '- Losing trades without a target and usable risk are skipped.\n' +
                  '- Calculation mode lets you choose OHLC or Tick replay.\n' +
                  '- OHLC uses stored 1-minute candles generated from tick data and is the default. It is faster, but intrabar price order is approximated.\n' +
                  '- Tick uses stored raw ticks for more precise but slower replay.\n' +
                  '- Trades without usable data for the selected mode are skipped.'
                }
                widthClass="w-80"
              />
            </div>
            <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">
              Explicit targets are reused as-is. Missing targets fall back to
              your Settings default of {whatIfTargetRMultiple}R when original
              risk is available; otherwise the trade is skipped.
            </p>

            <div className="flex items-end gap-4 mb-6">
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                  Stop Widening (R)
                </label>
                <input
                  type="number"
                  min="0.1"
                  max="10"
                  step="0.1"
                  value={rWidening}
                  onChange={(e) => setRWidening(e.target.value)}
                  className="input-field text-sm w-28"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                  Calculation Mode
                </label>
                <select
                  value={replayMode}
                  onChange={(e) => setReplayMode(e.target.value as WhatIfReplayMode)}
                  className="input-field text-sm w-32"
                >
                  <option value="ohlc">OHLC (1m)</option>
                  <option value="tick">Tick</option>
                </select>
              </div>
              <button
                type="button"
                onClick={handleSimulate}
                disabled={simLoading}
                className="btn-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
              >
                {simLoading ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Simulating…
                  </span>
                ) : (
                  'Calculate'
                )}
              </button>
            </div>

            {(simResult || simLoading) && (
              <div className="relative space-y-4">
                {simLoading && simResult ? <CardLoadingOverlay label="Running simulation…" /> : null}
                {simLoading && !simResult ? (
                  <div className="flex justify-center py-10">
                    <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
                  </div>
                ) : null}
                {simResult ? (
                <>
                {/* Summary line */}
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {simResult.tradesTotal} trades: {simResult.tradesConverted} converted to winners, {simResult.tradesSimulated} simulated, {simResult.tradesSkipped} skipped
                </p>

                {/* Comparison table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        <th className="px-4 py-2 text-left">Metric</th>
                        <th className="px-4 py-2 text-right">Original</th>
                        <th className="px-4 py-2 text-right">What-If</th>
                        <th className="px-4 py-2 text-right">Delta</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-gray-100 dark:border-gray-700/50">
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">Total P&L</td>
                        <td className="px-4 py-2 text-right">{formatCurrency(simResult.original.total_pnl)}</td>
                        <td className="px-4 py-2 text-right">{formatCurrency(simResult.whatIf.total_pnl)}</td>
                        <td className="px-4 py-2 text-right">
                          <DeltaCell value={simResult.delta.total_pnl} isCurrency />
                        </td>
                      </tr>
                      <tr className="border-b border-gray-100 dark:border-gray-700/50">
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">APPT</td>
                        <td className="px-4 py-2 text-right">{formatCurrency(simResult.original.avg_pnl)}</td>
                        <td className="px-4 py-2 text-right">{formatCurrency(simResult.whatIf.avg_pnl)}</td>
                        <td className="px-4 py-2 text-right">
                          <DeltaCell value={simResult.delta.avg_pnl} isCurrency />
                        </td>
                      </tr>
                      <tr className="border-b border-gray-100 dark:border-gray-700/50">
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">Win Rate</td>
                        <td className="px-4 py-2 text-right">{simResult.original.win_rate.toFixed(1)}%</td>
                        <td className="px-4 py-2 text-right">{simResult.whatIf.win_rate.toFixed(1)}%</td>
                        <td className="px-4 py-2 text-right">
                          <DeltaCell value={simResult.delta.win_rate} suffix="%" decimals={1} />
                        </td>
                      </tr>
                      <tr className="border-b border-gray-100 dark:border-gray-700/50">
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">Profit Factor</td>
                        <td className="px-4 py-2 text-right">{String(simResult.original.profit_factor)}</td>
                        <td className="px-4 py-2 text-right">{String(simResult.whatIf.profit_factor)}</td>
                        <td className="px-4 py-2 text-right">
                          <DeltaCell value={simResult.delta.profit_factor} />
                        </td>
                      </tr>
                      <tr className="border-b border-gray-100 dark:border-gray-700/50">
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">Expectancy (R)</td>
                        <td className="px-4 py-2 text-right">{formatRValue(simResult.original.expectancy_r)}</td>
                        <td className="px-4 py-2 text-right">{formatRValue(simResult.whatIf.expectancy_r)}</td>
                        <td className="px-4 py-2 text-right">
                          {simResult.delta.expectancy_r == null ? (
                            <span className="text-gray-500">—</span>
                          ) : (
                            <DeltaCell value={simResult.delta.expectancy_r} suffix="R" />
                          )}
                        </td>
                      </tr>
                      <tr className="border-b border-gray-100 dark:border-gray-700/50">
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">Winners</td>
                        <td className="px-4 py-2 text-right">{simResult.original.total_winners}</td>
                        <td className="px-4 py-2 text-right">{simResult.whatIf.total_winners}</td>
                        <td className="px-4 py-2 text-right">
                          <DeltaCell value={simResult.delta.winners_change} />
                        </td>
                      </tr>
                      <tr>
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">Losers</td>
                        <td className="px-4 py-2 text-right">{simResult.original.total_losers}</td>
                        <td className="px-4 py-2 text-right">{simResult.whatIf.total_losers}</td>
                        <td className="px-4 py-2 text-right">
                          <DeltaCell value={simResult.delta.losers_change} favorableWhenNegative />
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div className="space-y-3">
                  <ResultSection
                    title="Converted"
                    count={simResult.convertedDetails.length}
                    expanded={resultSectionsExpanded.converted}
                    onToggle={() => setResultSectionsExpanded((prev) => ({ ...prev, converted: !prev.converted }))}
                    trades={simResult.convertedDetails}
                  />
                  <ResultSection
                    title="Simulated"
                    count={simResult.simulatedDetails.length}
                    expanded={resultSectionsExpanded.simulated}
                    onToggle={() => setResultSectionsExpanded((prev) => ({ ...prev, simulated: !prev.simulated }))}
                    trades={simResult.simulatedDetails}
                  />
                  <ResultSection
                    title="Skipped"
                    count={simResult.skippedDetails.length}
                    expanded={resultSectionsExpanded.skipped}
                    onToggle={() => setResultSectionsExpanded((prev) => ({ ...prev, skipped: !prev.skipped }))}
                    trades={simResult.skippedDetails}
                  />
                </div>
                </>
                ) : null}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
