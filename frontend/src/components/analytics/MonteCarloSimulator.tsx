import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Loader2 } from 'lucide-react';

import { runMonteCarloSimulation } from '../../api/analytics.api';
import { useAuth } from '../../hooks/useAuth';
import { useChartColors } from '../../hooks/useChartColors';
import type {
  AnalyticsSummary,
  MonteCarloRiskMode,
  MonteCarloSimulationMetadata,
  MonteCarloSimulationMetrics,
  MonteCarloSimulationMode,
  MonteCarloSimulationPoint,
} from '../../types/analytics.types';
import type { FilterParams } from '../../types/common.types';
import { formatCurrency, formatPercent } from '../../utils/formatters';
import { InfoTooltip } from '../ui/InfoTooltip';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface MonteCarloSimulatorProps {
  summary: AnalyticsSummary | null;
  filters: FilterParams;
}

interface SimResult {
  chartData: MonteCarloSimulationPoint[];
  metrics: MonteCarloSimulationMetrics;
  metadata: MonteCarloSimulationMetadata;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const DEFAULT_SIMULATION_COUNT = 50;
const DEFAULT_NUM_TRADES = 500;
const DEFAULT_STARTING_EQUITY = 10000;
const DEFAULT_WIN_RATE_PCT = 50;
const DEFAULT_WIN_LOSS_RATIO_R = 2;

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function MetricCard({ label, value, color, tooltip }: { label: string; value: string; color?: string; tooltip?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap flex items-center gap-1">
        {label}
        {tooltip && <InfoTooltip text={tooltip} ariaLabel={`Info about ${label}`} iconSize="w-3 h-3" />}
      </span>
      <span className={`text-sm font-semibold ${color ?? 'text-gray-900 dark:text-gray-100'}`}>
        {value}
      </span>
    </div>
  );
}

function ChartLoadingOverlay() {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-white/70 dark:bg-gray-900/70 z-10 rounded-lg">
      <div className="flex flex-col items-center gap-2">
        <Loader2 className="h-8 w-8 animate-spin text-brand-600" />
        <span className="text-xs text-gray-500 dark:text-gray-400">Simulating…</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

export function MonteCarloSimulator({ summary, filters }: MonteCarloSimulatorProps) {
  const { user } = useAuth();
  const c = useChartColors();
  const hasHistoricalTrades = (summary?.total_trades ?? 0) > 0;

  const fallbackWinRate = useMemo(() => {
    if (!hasHistoricalTrades) return DEFAULT_WIN_RATE_PCT;
    if (summary && Number.isFinite(summary.win_rate)) return summary.win_rate;
    return DEFAULT_WIN_RATE_PCT;
  }, [hasHistoricalTrades, summary]);

  const fallbackWinLossRatio = useMemo(() => {
    if (!hasHistoricalTrades) return DEFAULT_WIN_LOSS_RATIO_R;
    if (summary?.wl_ratio_r != null && Number.isFinite(summary.wl_ratio_r) && summary.wl_ratio_r >= 0) {
      return summary.wl_ratio_r;
    }
    return DEFAULT_WIN_LOSS_RATIO_R;
  }, [hasHistoricalTrades, summary]);

  // ---- Parameters (all string state for controlled inputs) ----
  const [startingEquity, setStartingEquity] = useState(String(user?.starting_equity ?? DEFAULT_STARTING_EQUITY));
  const [winRate, setWinRate] = useState(fallbackWinRate.toFixed(1));
  const [winLossRatio, setWinLossRatio] = useState(fallbackWinLossRatio.toFixed(2));
  const [numTrades, setNumTrades] = useState(String(DEFAULT_NUM_TRADES));
  const [avgRiskFixed, setAvgRiskFixed] = useState('200');
  const [avgRiskPct, setAvgRiskPct] = useState('1.0');
  const [minRisk, setMinRisk] = useState(
    summary?.loss_per_share_avg != null && summary.loss_per_share_avg !== 0
      ? Math.abs(summary.loss_per_share_avg).toFixed(0)
      : '50',
  );
  const [riskMode, setRiskMode] = useState<MonteCarloRiskMode>('percent');
  const [simMode, setSimMode] = useState<MonteCarloSimulationMode>(hasHistoricalTrades ? 'bootstrap' : 'parametric');

  // Sync win rate / W:L ratio when imported-trade data changes
  useEffect(() => {
    if (!hasHistoricalTrades) {
      setWinRate(DEFAULT_WIN_RATE_PCT.toFixed(1));
      setWinLossRatio(DEFAULT_WIN_LOSS_RATIO_R.toFixed(2));
      setSimMode('parametric');
      return;
    }
    setWinRate(fallbackWinRate.toFixed(1));
    setWinLossRatio(fallbackWinLossRatio.toFixed(2));
  }, [hasHistoricalTrades, fallbackWinRate, fallbackWinLossRatio]);

  // Pre-fill avg risk from summary on first load
  const prefilled = useRef(false);
  useEffect(() => {
    if (!prefilled.current && summary) {
      prefilled.current = true;
      if (summary.avg_loser !== 0) setAvgRiskFixed(Math.abs(summary.avg_loser).toFixed(0));
      if (summary.loss_per_share_avg != null && summary.loss_per_share_avg !== 0) {
        setMinRisk(Math.abs(summary.loss_per_share_avg).toFixed(0));
      }
    }
  }, [summary]);

  // ---- Simulation state ----
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [simLoading, setSimLoading] = useState(false);

  // ---- Refs ----
  const seedRef = useRef(42);
  const requestIdRef = useRef(0);

  // ---- Dispatch simulation to backend ----
  const dispatchSimulation = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setSimLoading(true);

    const apiFilters = Object.fromEntries(
      Object.entries(filters).filter(([, value]) => value !== ''),
    );

    try {
      const response = await runMonteCarloSimulation(
        {
          mode: simMode,
          startingEquity: parseFloat(startingEquity) || DEFAULT_STARTING_EQUITY,
          winRate: parseFloat(winRate) || DEFAULT_WIN_RATE_PCT,
          winLossRatio: parseFloat(winLossRatio) || DEFAULT_WIN_LOSS_RATIO_R,
          riskFixed: parseFloat(avgRiskFixed) || 200,
          riskPct: parseFloat(avgRiskPct) || 1,
          minRisk: parseFloat(minRisk) || 0,
          riskMode,
          seed: seedRef.current,
          numTrades: Math.max(10, Math.min(1000, parseInt(numTrades, 10) || DEFAULT_NUM_TRADES)),
        },
        apiFilters,
      );

      if (requestId !== requestIdRef.current) {
        return;
      }

      startTransition(() => {
        setSimResult({
          chartData: response.chart_data,
          metrics: response.metrics,
          metadata: response.metadata,
        });
        if (response.metadata.effective_mode !== simMode) {
          setSimMode(response.metadata.effective_mode);
        }
        setSimLoading(false);
      });
    } catch {
      if (requestId === requestIdRef.current) {
        setSimLoading(false);
      }
    }
  }, [avgRiskFixed, avgRiskPct, filters, minRisk, numTrades, riskMode, simMode, startingEquity, winLossRatio, winRate]);

  // Run once automatically on mount
  useEffect(() => {
    void dispatchSimulation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Button handler — new random seed, then dispatch
  const handleNewSimulation = () => {
    seedRef.current += 1;
    void dispatchSimulation();
  };

  // ---- Chart tooltip ----
  const renderTooltip = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (props: any) => {
      const { active, payload, label } = props;
      if (!active || !payload?.length) return null;
      const avg = payload.find((p: { dataKey: string }) => p.dataKey === 'avgEquity');
      if (!avg) return null;
      return (
        <div
          className="rounded-md px-3 py-2 text-xs shadow-lg"
          style={{
            backgroundColor: c.tooltipBg,
            border: `1px solid ${c.tooltipBorder}`,
            color: c.tooltipText,
          }}
        >
          <p className="font-semibold mb-1">Trade #{label}</p>
          <p>Avg Equity: {formatCurrency(avg.value as number)}</p>
        </div>
      );
    },
    [c],
  );

  // Only generate keys for the display subset (matches worker MAX_DISPLAY_LINES)
  const simKeys = useMemo(
    () => Object.keys(simResult?.chartData[0] ?? {}).filter((key) => key.startsWith('sim_')),
    [simResult?.chartData],
  );

  const chartData = simResult?.chartData ?? [];
  const metrics = simResult?.metrics;
  const simulationCount = simResult?.metadata.simulation_count ?? DEFAULT_SIMULATION_COUNT;
  const parsedNumTrades = Math.max(10, Math.min(1000, parseInt(numTrades, 10) || DEFAULT_NUM_TRADES));

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* Left: Parameters panel */}
      <div className="lg:w-72 xl:w-80 shrink-0 space-y-4">
        <div className="card p-4 space-y-4">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            Simulation Parameters
          </h3>

          {/* Simulation Mode */}
          <div>
            <span className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Mode</span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => startTransition(() => setSimMode('bootstrap'))}
                disabled={!hasHistoricalTrades}
                className={`flex-1 px-3 py-1.5 text-xs rounded-md border transition-colors ${
                  simMode === 'bootstrap'
                    ? 'bg-brand-600 text-white border-brand-600'
                    : 'bg-gray-100 text-gray-600 border-gray-300 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600'
                } disabled:opacity-40 disabled:cursor-not-allowed`}
                title={!hasHistoricalTrades ? 'No closed trades available for bootstrap sampling' : 'Sample historical trades on the backend'}
              >
                Sampling
              </button>
              <button
                type="button"
                onClick={() => startTransition(() => setSimMode('parametric'))}
                className={`flex-1 px-3 py-1.5 text-xs rounded-md border transition-colors ${
                  simMode === 'parametric'
                    ? 'bg-brand-600 text-white border-brand-600'
                    : 'bg-gray-100 text-gray-600 border-gray-300 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600'
                }`}
              >
                Parametric
              </button>
            </div>
            <p className="mt-1 text-[10px] text-gray-400 dark:text-gray-500 leading-tight">
              {simMode === 'bootstrap'
                ? 'Samples filtered historical trades on the backend.'
                : 'Uses win rate, W:L ratio and risk parameters.'}
            </p>
          </div>

          {/* Starting Equity */}
          <div>
            <label htmlFor="mc-equity" className="block text-xs font-medium text-gray-600 dark:text-gray-400">
              Starting Equity ($)
            </label>
            <input
              id="mc-equity"
              type="number"
              min="0"
              step="any"
              className="input-field mt-1 text-sm"
              value={startingEquity}
              onChange={(e) => setStartingEquity(e.target.value)}
            />
          </div>

          {/* Parametric-only fields */}
          {simMode === 'parametric' && (
            <>
              <div>
                <label htmlFor="mc-winrate" className="block text-xs font-medium text-gray-600 dark:text-gray-400">
                  Win Rate (%)
                </label>
                <input
                  id="mc-winrate"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  className="input-field mt-1 text-sm"
                  value={winRate}
                  onChange={(e) => setWinRate(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="mc-wlratio" className="block text-xs font-medium text-gray-600 dark:text-gray-400">
                  Win : Loss Ratio (R)
                </label>
                <input
                  id="mc-wlratio"
                  type="number"
                  min="0"
                  step="0.01"
                  className="input-field mt-1 text-sm"
                  value={winLossRatio}
                  onChange={(e) => setWinLossRatio(e.target.value)}
                />
              </div>
            </>
          )}

          {/* Number of Trades */}
          <div>
            <label htmlFor="mc-numtrades" className="block text-xs font-medium text-gray-600 dark:text-gray-400">
              Number of Trades
            </label>
            <input
              id="mc-numtrades"
              type="number"
              min="10"
              max="1000"
              step="10"
              className="input-field mt-1 text-sm"
              value={numTrades}
              onChange={(e) => setNumTrades(e.target.value)}
            />
          </div>

          {/* Risk Mode Toggle */}
          <div>
            <span className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Risk Per Trade</span>
            <div className="flex gap-2 mb-2">
              <button
                type="button"
                onClick={() => startTransition(() => setRiskMode('fixed'))}
                className={`px-3 py-1 text-xs rounded-md border transition-colors ${
                  riskMode === 'fixed'
                    ? 'bg-brand-600 text-white border-brand-600'
                    : 'bg-gray-100 text-gray-600 border-gray-300 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600'
                }`}
              >
                Fixed ($)
              </button>
              <button
                type="button"
                onClick={() => startTransition(() => setRiskMode('percent'))}
                className={`px-3 py-1 text-xs rounded-md border transition-colors ${
                  riskMode === 'percent'
                    ? 'bg-brand-600 text-white border-brand-600'
                    : 'bg-gray-100 text-gray-600 border-gray-300 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600'
                }`}
              >
                % of Equity
              </button>
            </div>
            {riskMode === 'fixed' ? (
              <input
                id="mc-risk-fixed"
                type="number"
                min="0"
                step="any"
                className="input-field text-sm"
                value={avgRiskFixed}
                onChange={(e) => setAvgRiskFixed(e.target.value)}
                aria-label="Risk per trade in dollars"
              />
            ) : (
              <input
                id="mc-risk-pct"
                type="number"
                min="0"
                max="100"
                step="0.1"
                className="input-field text-sm"
                value={avgRiskPct}
                onChange={(e) => setAvgRiskPct(e.target.value)}
                aria-label="Risk per trade as percent of equity"
              />
            )}
          </div>

          {/* Minimum Risk — percent mode only */}
          {riskMode === 'percent' && (
            <div>
              <label htmlFor="mc-min-risk" className="block text-xs font-medium text-gray-600 dark:text-gray-400">
                Minimum Risk ($)
              </label>
              <input
                id="mc-min-risk"
                type="number"
                min="0"
                step="any"
                className="input-field mt-1 text-sm"
                value={minRisk}
                onChange={(e) => setMinRisk(e.target.value)}
              />
              <p className="mt-0.5 text-[10px] text-gray-400 dark:text-gray-500 leading-tight">
                risk = max(equity × {avgRiskPct}%, ${minRisk})
              </p>
            </div>
          )}

          {/* Info */}
          <p className="text-[10px] text-gray-400 dark:text-gray-500 leading-tight">
            {simulationCount.toLocaleString()} simulations × {parsedNumTrades.toLocaleString()} trades each.
          </p>

          {/* Run button */}
          <button
            type="button"
            onClick={handleNewSimulation}
            disabled={simLoading}
            className="w-full btn-primary py-2 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {simLoading ? 'Simulating…' : 'New Simulation'}
          </button>
        </div>
      </div>

      {/* Right: Chart + Metrics */}
      <div className="flex-1 min-w-0 space-y-4">
        {/* Chart */}
        <div className="card p-4 relative">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
            Monte Carlo Equity Simulation
          </h3>
          {simLoading && <ChartLoadingOverlay />}
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={c.grid} />
                <XAxis
                  dataKey="trade"
                  tick={{ fontSize: 11, fill: c.tick }}
                  label={{ value: '# Trades', position: 'insideBottomRight', offset: -5, fontSize: 11, fill: c.tick }}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: c.tick }}
                  tickFormatter={(v: number) => formatCurrency(v)}
                  label={{ value: 'Equity', angle: -90, position: 'insideLeft', fontSize: 11, fill: c.tick }}
                />
                <Tooltip content={renderTooltip} />

                {/* Individual simulation lines — limited subset for perf */}
                {simKeys.map((key) => (
                  <Line
                    key={key}
                    type="linear"
                    dataKey={key}
                    stroke={c.isDark ? '#6366f1' : '#818cf8'}
                    strokeWidth={0.5}
                    strokeOpacity={0.5}
                    dot={false}
                    isAnimationActive={false}
                    activeDot={false}
                  />
                ))}

                {/* Average equity line */}
                <Line
                  type="linear"
                  dataKey="avgEquity"
                  stroke="#f59e0b"
                  strokeWidth={2.5}
                  dot={false}
                  isAnimationActive={false}
                  activeDot={{ r: 4, fill: '#f59e0b' }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[400px] flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">
              {simLoading ? '' : 'Run a simulation to see results'}
            </div>
          )}
        </div>

        {/* Metrics grid */}
        {metrics && (
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Simulation Metrics
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
              <MetricCard
                label="Kelly Criterion"
                value={formatPercent(metrics.kelly * 100, 1)}
                color={metrics.kelly > 0 ? 'pnl-positive' : 'pnl-negative'}
                tooltip="Optimal fraction of capital to risk per trade for maximum long-term growth."
              />
              <MetricCard
                label="Expectation (R)"
                value={metrics.expectation.toFixed(3)}
                color={metrics.expectation > 0 ? 'pnl-positive' : 'pnl-negative'}
                tooltip="Average R-multiple expected per trade. Positive means profitable on average."
              />
              <MetricCard
                label="Biggest Max DD"
                value={`${formatPercent(metrics.biggestMaxDrawdownPct, 1)} (${formatCurrency(metrics.biggestMaxDrawdown)})`}
                color="pnl-negative"
                tooltip="Largest peak-to-trough drawdown observed across all simulations, as % of the running high-water mark."
              />
              <MetricCard
                label="Avg Max Drawdown"
                value={`${formatPercent(metrics.avgMaxDrawdownPct, 1)} (${formatCurrency(metrics.avgMaxDrawdown)})`}
                color="pnl-negative"
                tooltip="Average of the maximum drawdown from each simulation run, as % of the running high-water mark."
              />
              <MetricCard
                label="Min Equity"
                value={formatCurrency(metrics.minEquity)}
                tooltip="Lowest equity value reached across all simulations."
              />
              <MetricCard
                label="Max Equity"
                value={formatCurrency(metrics.maxEquity)}
                tooltip="Highest equity value reached across all simulations."
              />
              <MetricCard
                label="Avg Performance"
                value={`${formatPercent(metrics.avgPerformancePct, 1)} (${formatCurrency(metrics.avgFinalEquity)})`}
                color={metrics.avgFinalEquity >= (parseFloat(startingEquity) || 0) ? 'pnl-positive' : 'pnl-negative'}
                tooltip={"Average final equity as % of starting equity, with dollar value.\nFormula: Avg Final Equity / Starting Equity × 100"}
              />
              <MetricCard
                label="Return / Max DD"
                value={metrics.returnOnMaxDrawdown.toFixed(2) + 'x'}
                color={metrics.returnOnMaxDrawdown >= 1 ? 'pnl-positive' : 'pnl-negative'}
                tooltip={"Ratio of average final equity to biggest max drawdown. Higher is better.\nFormula: Avg Final Equity / Biggest Max Drawdown"}
              />
              <MetricCard
                label="% Profitable"
                value={formatPercent(metrics.pctProfitable, 1)}
                color={metrics.pctProfitable >= 50 ? 'pnl-positive' : 'pnl-negative'}
                tooltip="Percentage of simulations ending with equity above starting equity."
              />
              <MetricCard
                label="% Ruined"
                value={formatPercent(metrics.pctRuined, 1)}
                color={metrics.pctRuined === 0 ? 'pnl-positive' : 'pnl-negative'}
                tooltip="Percentage of simulations where equity reached zero (account blown)."
              />
              <MetricCard
                label="Max Consec. Wins"
                value={String(metrics.maxConsecutiveWins)}
                color="pnl-positive"
                tooltip="Longest winning streak observed across all simulations."
              />
              <MetricCard
                label="Max Consec. Losses"
                value={String(metrics.maxConsecutiveLosses)}
                color="pnl-negative"
                tooltip="Longest losing streak observed across all simulations."
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
