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

import { useAuth } from '../../hooks/useAuth';
import { useChartColors } from '../../hooks/useChartColors';
import type { AnalyticsSummary, TradePnl } from '../../types/analytics.types';
import { formatCurrency, formatPercent } from '../../utils/formatters';
import { InfoTooltip } from '../ui/InfoTooltip';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface MonteCarloSimulatorProps {
  summary: AnalyticsSummary | null;
  /** Per-trade P&L values for bootstrap resampling. */
  tradePnls: TradePnl[];
}

/** One point on the average-equity series (also holds all sim values). */
interface SimPoint {
  trade: number;
  avgEquity: number;
  /** Individual simulation lines stored as sim_0 … sim_N-1. */
  [key: string]: number;
}

interface SimMetrics {
  kelly: number;
  expectation: number;
  biggestMaxDrawdown: number;
  avgMaxDrawdown: number;
  minEquity: number;
  maxEquity: number;
  avgFinalEquity: number;
  avgPerformancePct: number;
  returnOnMaxDrawdown: number;
  maxConsecutiveWins: number;
  maxConsecutiveLosses: number;
  pctProfitable: number;
  pctRuined: number;
}

interface SimResult {
  chartData: SimPoint[];
  metrics: SimMetrics;
}

type SimMode = 'bootstrap' | 'parametric';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const NUM_SIMULATIONS = 100;
const NUM_TRADES = 1000;

/** Deterministic pseudo-random number generator (Mulberry32). */
function mulberry32(seed: number) {
  return () => {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ------------------------------------------------------------------ */
/*  Simulation engine (runs off main thread via setTimeout chunks)     */
/* ------------------------------------------------------------------ */

function runParametricSim(params: {
  startingEquity: number;
  winRate: number;
  winLossRatio: number;
  riskFixed: number;
  riskPct: number;
  minRisk: number;
  riskMode: 'fixed' | 'percent';
}): number[][] {
  const { startingEquity, winRate, winLossRatio, riskFixed, riskPct, minRisk, riskMode } = params;
  const wr = winRate / 100;
  const rng = mulberry32(42);
  const simulations: number[][] = [];

  for (let s = 0; s < NUM_SIMULATIONS; s++) {
    const equity: number[] = [startingEquity];
    for (let t = 0; t < NUM_TRADES; t++) {
      const cur = equity[equity.length - 1]!;
      if (cur <= 0) {
        // Ruined — fill remaining trades with 0
        for (let r = t; r < NUM_TRADES; r++) equity.push(0);
        break;
      }
      const risk =
        riskMode === 'fixed'
          ? riskFixed
          : Math.max((riskPct / 100) * cur, minRisk);
      if (rng() < wr) {
        equity.push(cur + risk * winLossRatio);
      } else {
        equity.push(Math.max(0, cur - risk));
      }
    }
    simulations.push(equity);
  }
  return simulations;
}

function runBootstrapSim(params: {
  startingEquity: number;
  rMultiples: number[];
  riskFixed: number;
  riskPct: number;
  minRisk: number;
  riskMode: 'fixed' | 'percent';
}): number[][] {
  const { startingEquity, rMultiples, riskFixed, riskPct, minRisk, riskMode } = params;
  const rng = mulberry32(42);
  const simulations: number[][] = [];
  const n = rMultiples.length;

  for (let s = 0; s < NUM_SIMULATIONS; s++) {
    const equity: number[] = [startingEquity];
    for (let t = 0; t < NUM_TRADES; t++) {
      const cur = equity[equity.length - 1]!;
      if (cur <= 0) {
        // Ruined — fill remaining trades with 0
        for (let r = t; r < NUM_TRADES; r++) equity.push(0);
        break;
      }
      // Dollar risk per trade: fixed or max(equity × pct, minRisk)
      const risk =
        riskMode === 'fixed'
          ? riskFixed
          : Math.max((riskPct / 100) * cur, minRisk);
      // Randomly sample a real trade's R-multiple
      const idx = Math.floor(rng() * n);
      const rMul = rMultiples[idx]!;
      equity.push(Math.max(0, cur + rMul * risk));
    }
    simulations.push(equity);
  }
  return simulations;
}

function computeMetrics(
  simulations: number[][],
  startingEquity: number,
  winRate: number,
  winLossRatio: number,
): SimMetrics {
  const wr = winRate / 100;
  const kelly = winLossRatio > 0 ? wr - (1 - wr) / winLossRatio : 0;
  const expectation = wr * winLossRatio - (1 - wr);

  const maxDrawdowns: number[] = [];
  const finalEquities: number[] = [];
  let globalMinEquity = Infinity;
  let globalMaxEquity = -Infinity;
  let globalMaxConsWins = 0;
  let globalMaxConsLosses = 0;
  let ruinedCount = 0;

  for (const equity of simulations) {
    let peak = equity[0]!;
    let maxDD = 0;
    let consWins = 0;
    let consLosses = 0;
    let simMaxConsWins = 0;
    let simMaxConsLosses = 0;
    let hitZero = false;

    for (let i = 1; i < equity.length; i++) {
      const val = equity[i]!;
      const prev = equity[i - 1]!;
      if (val <= 0) { hitZero = true; }
      if (val > peak) peak = val;
      const dd = peak - val;
      if (dd > maxDD) maxDD = dd;
      if (val < globalMinEquity) globalMinEquity = val;
      if (val > globalMaxEquity) globalMaxEquity = val;
      if (val > prev) {
        consWins++;
        consLosses = 0;
        if (consWins > simMaxConsWins) simMaxConsWins = consWins;
      } else if (val < prev) {
        consLosses++;
        consWins = 0;
        if (consLosses > simMaxConsLosses) simMaxConsLosses = consLosses;
      }
    }

    if (hitZero) ruinedCount++;
    maxDrawdowns.push(maxDD);
    finalEquities.push(equity[equity.length - 1]!);
    if (simMaxConsWins > globalMaxConsWins) globalMaxConsWins = simMaxConsWins;
    if (simMaxConsLosses > globalMaxConsLosses) globalMaxConsLosses = simMaxConsLosses;
  }

  const biggestMaxDrawdown = Math.max(...maxDrawdowns);
  const avgMaxDrawdown = maxDrawdowns.reduce((a, b) => a + b, 0) / maxDrawdowns.length;
  const avgFinalEquity = finalEquities.reduce((a, b) => a + b, 0) / finalEquities.length;
  const avgPerformancePct = ((avgFinalEquity - startingEquity) / startingEquity) * 100;
  const returnOnMaxDrawdown = avgMaxDrawdown > 0 ? (avgFinalEquity - startingEquity) / avgMaxDrawdown : 0;
  const pctProfitable = (finalEquities.filter((e) => e > startingEquity).length / simulations.length) * 100;
  const pctRuined = (ruinedCount / simulations.length) * 100;

  return {
    kelly, expectation, biggestMaxDrawdown, avgMaxDrawdown,
    minEquity: globalMinEquity, maxEquity: globalMaxEquity,
    avgFinalEquity, avgPerformancePct, returnOnMaxDrawdown,
    maxConsecutiveWins: globalMaxConsWins,
    maxConsecutiveLosses: globalMaxConsLosses,
    pctProfitable,
    pctRuined,
  };
}

/** Build chart data by sampling simulation arrays. */
function buildChartData(simulations: number[][]): SimPoint[] {
  const step = Math.max(1, Math.floor(NUM_TRADES / 500));
  const points: SimPoint[] = [];

  for (let t = 0; t <= NUM_TRADES; t += step) {
    const point: SimPoint = { trade: t, avgEquity: 0 };
    let sum = 0;
    for (let s = 0; s < NUM_SIMULATIONS; s++) {
      const val = simulations[s]![t]!;
      point[`sim_${s}`] = val;
      sum += val;
    }
    point.avgEquity = sum / NUM_SIMULATIONS;
    points.push(point);
  }

  const lastPoint = points[points.length - 1];
  if (lastPoint && lastPoint.trade !== NUM_TRADES) {
    const point: SimPoint = { trade: NUM_TRADES, avgEquity: 0 };
    let sum = 0;
    for (let s = 0; s < NUM_SIMULATIONS; s++) {
      const val = simulations[s]![NUM_TRADES]!;
      point[`sim_${s}`] = val;
      sum += val;
    }
    point.avgEquity = sum / NUM_SIMULATIONS;
    points.push(point);
  }

  return points;
}

/** Run full simulation async (yields to the event loop via setTimeout). */
function runSimulationAsync(params: {
  mode: SimMode;
  startingEquity: number;
  winRate: number;
  winLossRatio: number;
  riskFixed: number;
  riskPct: number;
  minRisk: number;
  riskMode: 'fixed' | 'percent';
  rMultiples: number[];
}): Promise<SimResult> {
  return new Promise((resolve) => {
    // Defer heavy computation to next tick to avoid blocking the UI
    setTimeout(() => {
      const { mode, startingEquity, winRate, winLossRatio, riskFixed, riskPct, minRisk, riskMode, rMultiples } = params;

      const simulations =
        mode === 'bootstrap' && rMultiples.length > 0
          ? runBootstrapSim({ startingEquity, rMultiples, riskFixed, riskPct, minRisk, riskMode })
          : runParametricSim({ startingEquity, winRate, winLossRatio, riskFixed, riskPct, minRisk, riskMode });

      // For bootstrap mode, derive effective winRate and winLossRatio from R-multiples for Kelly/expectation
      let effectiveWinRate = winRate;
      let effectiveWlr = winLossRatio;
      if (mode === 'bootstrap' && rMultiples.length > 0) {
        const wins = rMultiples.filter((r) => r > 0);
        const losses = rMultiples.filter((r) => r < 0);
        effectiveWinRate = (wins.length / rMultiples.length) * 100;
        const avgWinR = wins.length > 0 ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;
        const avgLossR = losses.length > 0 ? Math.abs(losses.reduce((a, b) => a + b, 0) / losses.length) : 0;
        effectiveWlr = avgLossR > 0 ? avgWinR / avgLossR : 0;
      }

      const metrics = computeMetrics(simulations, startingEquity, effectiveWinRate, effectiveWlr);
      const chartData = buildChartData(simulations);

      resolve({ chartData, metrics });
    }, 0);
  });
}

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

/** Spinning loader overlay for the chart area. */
function ChartLoadingOverlay() {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-white/60 dark:bg-gray-900/60 z-10 rounded-lg">
      <div className="flex flex-col items-center gap-2">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 dark:border-gray-600 border-t-brand-600" />
        <span className="text-xs text-gray-500 dark:text-gray-400">Simulating…</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

/** Monte Carlo equity simulation with editable parameters and chart. */
export function MonteCarloSimulator({ summary, tradePnls }: MonteCarloSimulatorProps) {
  const { user } = useAuth();
  const c = useChartColors();

  // ---- Parameters ----
  const [startingEquity, setStartingEquity] = useState(
    String(user?.starting_equity ?? 50000),
  );
  const [winRate, setWinRate] = useState(
    summary ? summary.win_rate.toFixed(1) : '55.0',
  );
  const [winLossRatio, setWinLossRatio] = useState(
    summary?.wl_ratio_r != null ? summary.wl_ratio_r.toFixed(2) : '1.50',
  );
  const [avgRiskFixed, setAvgRiskFixed] = useState('200');
  const [avgRiskPct, setAvgRiskPct] = useState('1.0');
  const [minRisk, setMinRisk] = useState(
    summary?.loss_per_share_avg != null && summary.loss_per_share_avg !== 0
      ? Math.abs(summary.loss_per_share_avg).toFixed(0)
      : '50',
  );
  const [riskMode, setRiskMode] = useState<'fixed' | 'percent'>('percent');
  const [simMode, setSimMode] = useState<SimMode>(
    tradePnls.length > 0 ? 'bootstrap' : 'parametric',
  );

  // Pre-fill avg risk from summary on first load
  const prefilled = useRef(false);
  useEffect(() => {
    if (!prefilled.current && summary) {
      prefilled.current = true;
      if (summary.avg_loser !== 0) {
        setAvgRiskFixed(Math.abs(summary.avg_loser).toFixed(0));
      }
      if (summary.loss_per_share_avg != null && summary.loss_per_share_avg !== 0) {
        setMinRisk(Math.abs(summary.loss_per_share_avg).toFixed(0));
      }
    }
  }, [summary]);

  // ---- Async simulation state ----
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const runIdRef = useRef(0); // to discard stale results

  // Extract R-multiples (only trades that have initial risk) for bootstrap
  const rMultiples = useMemo(
    () => tradePnls
      .filter((t) => t.r_multiple != null)
      .map((t) => t.r_multiple as number),
    [tradePnls],
  );

  // Debounce + run simulation when parameters change
  useEffect(() => {
    const id = ++runIdRef.current;
    setSimLoading(true);

    const se = parseFloat(startingEquity) || 50000;
    const wr = parseFloat(winRate) || 55;
    const wlr = parseFloat(winLossRatio) || 1.5;
    const rf = parseFloat(avgRiskFixed) || 200;
    const rp = parseFloat(avgRiskPct) || 1;
    const mr = parseFloat(minRisk) || 0;

    const timer = setTimeout(() => {
      void runSimulationAsync({
        mode: simMode,
        startingEquity: se,
        winRate: wr,
        winLossRatio: wlr,
        riskFixed: rf,
        riskPct: rp,
        minRisk: mr,
        riskMode,
        rMultiples,
      }).then((result) => {
        // Only apply if this is the latest run
        if (id === runIdRef.current) {
          setSimResult(result);
          setSimLoading(false);
        }
      });
    }, 400); // 400ms debounce — lets the user finish typing

    return () => clearTimeout(timer);
  }, [startingEquity, winRate, winLossRatio, avgRiskFixed, avgRiskPct, minRisk, riskMode, simMode, rMultiples]);

  // ---- Tooltip: only show average line info ----
  const renderTooltip = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (props: any) => {
      const { active, payload, label } = props;
      if (!active || !payload?.length) return null;
      const avg = payload.find(
        (p: { dataKey: string }) => p.dataKey === 'avgEquity',
      );
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

  // Simulation line keys
  const simKeys = useMemo(
    () => Array.from({ length: NUM_SIMULATIONS }, (_, i) => `sim_${i}`),
    [],
  );

  const chartData = simResult?.chartData ?? [];
  const metrics = simResult?.metrics;

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
            <span className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              Mode
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => startTransition(() => setSimMode('bootstrap'))}
                disabled={rMultiples.length === 0}
                className={`flex-1 px-3 py-1.5 text-xs rounded-md border transition-colors ${
                  simMode === 'bootstrap'
                    ? 'bg-brand-600 text-white border-brand-600'
                    : 'bg-gray-100 text-gray-600 border-gray-300 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600'
                } disabled:opacity-40 disabled:cursor-not-allowed`}
                title={rMultiples.length === 0 ? 'No trades with R-multiples available' : 'Resample R-multiples from actual trades'}
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
                ? `Picks a random R-multiple from ${rMultiples.length} real trades × risk per step.`
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
              {/* Win Rate */}
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

              {/* Win : Loss Ratio */}
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

          {/* Risk Mode Toggle — shared by both modes */}
          <div>
            <span className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              Risk Per Trade
            </span>
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

          {/* Minimum Risk — only shown in percent mode */}
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
            {NUM_SIMULATIONS} simulations × {NUM_TRADES.toLocaleString()} trades each.
          </p>
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

                {/* Individual simulation lines — thin, semi-transparent */}
                {simKeys.map((key) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={c.isDark ? '#6366f1' : '#818cf8'}
                    strokeWidth={0.5}
                    strokeOpacity={0.15}
                    dot={false}
                    isAnimationActive={false}
                    activeDot={false}
                  />
                ))}

                {/* Average equity line — bold, on top */}
                <Line
                  type="monotone"
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
                value={formatCurrency(metrics.biggestMaxDrawdown)}
                color="pnl-negative"
                tooltip="Largest peak-to-trough drawdown observed across all simulations."
              />
              <MetricCard
                label="Avg Max Drawdown"
                value={formatCurrency(metrics.avgMaxDrawdown)}
                color="pnl-negative"
                tooltip="Average of the maximum drawdown from each simulation run."
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
                label="Avg Final Equity"
                value={formatCurrency(metrics.avgFinalEquity)}
                color={metrics.avgFinalEquity >= (parseFloat(startingEquity) || 0) ? 'pnl-positive' : 'pnl-negative'}
                tooltip="Mean ending equity averaged across all simulation runs."
              />
              <MetricCard
                label="Avg Performance"
                value={formatPercent(metrics.avgPerformancePct, 1)}
                color={metrics.avgPerformancePct >= 0 ? 'pnl-positive' : 'pnl-negative'}
                tooltip="Average percentage return from starting equity across all runs."
              />
              <MetricCard
                label="Return / Max DD"
                value={metrics.returnOnMaxDrawdown.toFixed(2) + 'x'}
                color={metrics.returnOnMaxDrawdown >= 1 ? 'pnl-positive' : 'pnl-negative'}
                tooltip="Ratio of average return to average max drawdown. Higher is better."
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
