import { ChevronDown, ChevronRight, FlaskConical, Loader2 } from 'lucide-react';
import { startTransition, useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { getStopAnalysis, getWickedOutTrades, runSimulation } from '../api/whatif.api';
import { FilterBar } from '../components/filters/FilterBar';
import { InfoTooltip } from '../components/ui/InfoTooltip';
import type { WorkerInput, WorkerOutput } from '../components/whatif/whatif.worker';
import { useToast } from '../hooks/useToast';
import type {
  StopAnalysisResponse,
  WickedOutTrade,
} from '../types/whatif.types';
import { formatCurrency, formatPnL } from '../utils/formatters';

function createWorker() {
  return new Worker(
    new URL('../components/whatif/whatif.worker.ts', import.meta.url),
    { type: 'module' },
  );
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function MetricCard({ label, value, tooltip }: { label: string; value: string; tooltip?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap flex items-center gap-1">
        {label}
        {tooltip && <InfoTooltip text={tooltip} ariaLabel={`Info about ${label}`} iconSize="w-3 h-3" />}
      </span>
      <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{value}</span>
    </div>
  );
}

function DeltaCell({ value, isCurrency = false }: { value: number; isCurrency?: boolean }) {
  const positive = value > 0;
  const cls = positive ? 'pnl-positive' : value < 0 ? 'pnl-negative' : 'text-gray-500';
  const text = isCurrency
    ? `${positive ? '+' : ''}${formatCurrency(value)}`
    : `${positive ? '+' : ''}${value.toFixed(2)}`;
  return <span className={cls}>{text}</span>;
}

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

/** What-if page: stop analysis, wicked-out trades, and simulation. */
export function WhatIfPage() {
  const { addToast } = useToast();

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

  // ---- Stop Analysis ----
  const [analysis, setAnalysis] = useState<StopAnalysisResponse | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);

  // ---- Wicked-out trades ----
  const [woTrades, setWoTrades] = useState<WickedOutTrade[]>([]);
  const [woExpanded, setWoExpanded] = useState(false);
  const [woLoading, setWoLoading] = useState(false);

  // ---- Simulation ----
  const [rWidening, setRWidening] = useState('0.5');
  const [simLoading, setSimLoading] = useState(false);
  const [simResult, setSimResult] = useState<WorkerOutput | null>(null);
  const simCache = useRef<Map<string, WorkerOutput>>(new Map());
  const workerRef = useRef<Worker | null>(null);

  // Fetch analysis + wicked-out trades on filter change
  const fetchData = useCallback(async (f: Record<string, string>) => {
    setAnalysisLoading(true);
    setWoLoading(true);
    try {
      const [analysisRes, woRes] = await Promise.all([
        getStopAnalysis(f),
        getWickedOutTrades(f),
      ]);
      setAnalysis(analysisRes);
      setWoTrades(woRes.trades);
    } catch {
      // Silenced — 401 handled by interceptor
    } finally {
      setAnalysisLoading(false);
      setWoLoading(false);
    }
  }, []);

  useEffect(() => {
    if (filters.symbol) {
      void fetchData(apiFilters);
    } else {
      setAnalysis(null);
      setWoTrades([]);
    }
    // Reset simulation results on filter change
    setSimResult(null);
    simCache.current.clear();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.symbol, filters.side, filters.account, filters.date_from, filters.date_to]);

  // Simulation handler
  async function handleSimulate() {
    const rVal = parseFloat(rWidening);
    if (isNaN(rVal) || rVal <= 0 || rVal > 10) {
      addToast('error', 'R-widening must be between 0.1 and 10');
      return;
    }

    const cacheKey = `${rVal}_${JSON.stringify(apiFilters)}`;
    const cached = simCache.current.get(cacheKey);
    if (cached) {
      setSimResult(cached);
      return;
    }

    setSimLoading(true);
    try {
      const response = await runSimulation(rVal, apiFilters);

      // Pass to web worker for delta computation
      workerRef.current?.terminate();
      const worker = createWorker();
      workerRef.current = worker;
      worker.onmessage = (e: MessageEvent<WorkerOutput>) => {
        startTransition(() => {
          setSimResult(e.data);
          simCache.current.set(cacheKey, e.data);
          setSimLoading(false);
        });
      };
      worker.postMessage({
        original: response.original,
        what_if: response.what_if,
        details: response.details,
        trades_total: response.trades_total,
        trades_converted: response.trades_converted,
        trades_simulated: response.trades_simulated,
        trades_skipped: response.trades_skipped,
      } as WorkerInput);
    } catch {
      addToast('error', 'Simulation failed');
      setSimLoading(false);
    }
  }

  // Cleanup worker on unmount
  useEffect(() => {
    return () => {
      workerRef.current?.terminate();
      workerRef.current = null;
    };
  }, []);

  // Wicked-out summary counts
  const woWithData = woTrades.filter((t) => t.has_ohlc_data).length;
  const woMissing = woTrades.length - woWithData;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <div className="flex items-center gap-2">
          <FlaskConical className="h-6 w-6 text-brand-600" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">What-if</h1>
        </div>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Analyse stop placement in R-multiples and simulate wider stops across losing trades.
        </p>
      </div>

      {/* Filters — symbol required */}
      <FilterBar
        filters={filters}
        onFilterChange={handleFilterChange}
        onClearFilters={handleClearFilters}
        requireSymbol
      />

      {!filters.symbol && (
        <div className="card p-8 text-center text-gray-400 dark:text-gray-500">
          Select an instrument above to view stop analysis.
        </div>
      )}

      {filters.symbol && (
        <>
          {/* ---- Wicked-Out Trades ---- */}
          <div className="card overflow-hidden">
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
                  `${woTrades.length} trade${woTrades.length !== 1 ? 's' : ''} (${woWithData} with data, ${woMissing} missing OHLC)`
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
                    No wicked-out trades found for this instrument.
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
                          <th className="px-4 py-2 text-center">OHLC</th>
                        </tr>
                      </thead>
                      <tbody>
                        {woTrades.map((t) => {
                          const pnl = formatPnL(t.net_pnl);
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
                              <td className="px-4 py-2 text-center">
                                {t.has_ohlc_data ? (
                                  <span className="text-green-600 dark:text-green-400" title="1-min OHLC available">✓</span>
                                ) : (
                                  <span className="text-amber-500 dark:text-amber-400" title="Missing 1-min OHLC">⚠</span>
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
          <div className="card p-6">
            <div className="flex items-center gap-1 mb-4">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
                Stop Management — Overshoot in R
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
                No wicked-out trades with wishful stop data for this instrument.
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
                    tooltip="Average overshoot in R-multiples across all wicked-out trades."
                  />
                  <MetricCard
                    label="Median"
                    value={`${analysis.median.toFixed(2)}R`}
                    tooltip="Middle value — half of overshoots are below this."
                  />
                  <MetricCard
                    label="P75"
                    value={`${analysis.p75.toFixed(2)}R`}
                    tooltip="75th percentile — 75% of overshoots are below this."
                  />
                  <MetricCard
                    label="P90"
                    value={`${analysis.p90.toFixed(2)}R`}
                    tooltip="90th percentile — 90% of overshoots are below this."
                  />
                  <MetricCard
                    label="P95"
                    value={`${analysis.p95.toFixed(2)}R`}
                    tooltip="95th percentile — 95% of overshoots are below this."
                  />
                  <MetricCard
                    label="IQR"
                    value={`${analysis.iqr.toFixed(2)}R`}
                    tooltip="Interquartile range (P75 − P25). Shows the spread of the middle 50% of overshoots."
                  />
                  <MetricCard
                    label="95% CI"
                    value={`${analysis.ci_lower.toFixed(2)}R – ${analysis.ci_upper.toFixed(2)}R`}
                    tooltip="Bootstrap 95% confidence interval for the mean overshoot. 10,000 resamples."
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
                  'Simulate widening your stop by xR across all losing trades:\n' +
                  '- Winners keep their P&L.\n' +
                  '- Losers with a target price and 1-min OHLC data ' +
                  'are replayed with the wider stop to check if they would have reached the target.'
                }
                widthClass="w-80"
              />
            </div>

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

            {simResult && (
              <div className="space-y-4">
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
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">Avg P&L</td>
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
                          <DeltaCell value={simResult.delta.win_rate} />
                        </td>
                      </tr>
                      <tr className="border-b border-gray-100 dark:border-gray-700/50">
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-300">Profit Factor</td>
                        <td className="px-4 py-2 text-right">{String(simResult.original.profit_factor)}</td>
                        <td className="px-4 py-2 text-right">{String(simResult.whatIf.profit_factor)}</td>
                        <td className="px-4 py-2 text-right">
                          <span className={simResult.delta.profit_factor_improved ? 'pnl-positive' : 'pnl-negative'}>
                            {simResult.delta.profit_factor_improved ? '↑ Improved' : '↓ Declined'}
                          </span>
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
                          <DeltaCell value={simResult.delta.losers_change} />
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Converted trades */}
                {simResult.convertedDetails.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                      Converted Trades ({simResult.convertedDetails.length})
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            <th className="px-3 py-1 text-left">Trade</th>
                            <th className="px-3 py-1 text-right">Original P&L</th>
                            <th className="px-3 py-1 text-right">New P&L</th>
                            <th className="px-3 py-1 text-right">Change</th>
                          </tr>
                        </thead>
                        <tbody>
                          {simResult.convertedDetails.map((d) => (
                            <tr key={d.trade_id} className="border-b border-gray-100 dark:border-gray-700/50">
                              <td className="px-3 py-1">
                                <Link to={`/trades/${d.trade_id}`} className="text-brand-600 hover:underline">
                                  {d.trade_id.slice(-6)}
                                </Link>
                              </td>
                              <td className={`px-3 py-1 text-right ${formatPnL(d.original_pnl).className}`}>
                                {formatPnL(d.original_pnl).text}
                              </td>
                              <td className={`px-3 py-1 text-right ${formatPnL(d.new_pnl).className}`}>
                                {formatPnL(d.new_pnl).text}
                              </td>
                              <td className="px-3 py-1 text-right">
                                <DeltaCell value={d.new_pnl - d.original_pnl} isCurrency />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
