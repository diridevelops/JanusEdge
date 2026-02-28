/**
 * Monte Carlo simulation Web Worker.
 *
 * All CPU-heavy work (simulation, metrics, chart data) runs here,
 * keeping the main thread free for UI rendering and input handling.
 */

/* ------------------------------------------------------------------ */
/*  Types (duplicated — workers are isolated modules)                  */
/* ------------------------------------------------------------------ */

interface SimPoint {
  trade: number;
  avgEquity: number;
  [key: string]: number;
}

interface SimMetrics {
  kelly: number;
  expectation: number;
  biggestMaxDrawdown: number;
  biggestMaxDrawdownPct: number;
  avgMaxDrawdown: number;
  avgMaxDrawdownPct: number;
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

export interface WorkerParams {
  mode: 'bootstrap' | 'parametric';
  startingEquity: number;
  winRate: number;
  winLossRatio: number;
  riskFixed: number;
  riskPct: number;
  minRisk: number;
  riskMode: 'fixed' | 'percent';
  rMultiples: number[];
  seed: number;
  numTrades: number;
}

export interface WorkerResult {
  chartData: SimPoint[];
  metrics: SimMetrics;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const NUM_SIMULATIONS = 50;
/** Only this many sim lines go into chart data (the rest are metrics-only). */
const MAX_DISPLAY_LINES = 15;
/** Cap chart data points to keep SVG rendering fast. */
const MAX_CHART_POINTS = 300;

/* ------------------------------------------------------------------ */
/*  PRNG (Mulberry32)                                                  */
/* ------------------------------------------------------------------ */

function mulberry32(seed: number) {
  return () => {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ------------------------------------------------------------------ */
/*  Simulation engines                                                 */
/* ------------------------------------------------------------------ */

function runParametricSim(p: {
  startingEquity: number; winRate: number; winLossRatio: number;
  riskFixed: number; riskPct: number; minRisk: number;
  riskMode: 'fixed' | 'percent'; seed: number; numTrades: number;
}): number[][] {
  const { startingEquity, winRate, winLossRatio, riskFixed, riskPct, minRisk, riskMode, seed, numTrades } = p;
  const wr = winRate / 100;
  const rng = mulberry32(seed);
  const sims: number[][] = [];

  for (let s = 0; s < NUM_SIMULATIONS; s++) {
    const eq: number[] = [startingEquity];
    for (let t = 0; t < numTrades; t++) {
      const cur = eq[eq.length - 1]!;
      if (cur <= 0) { for (let r = t; r < numTrades; r++) eq.push(0); break; }
      const risk = riskMode === 'fixed' ? riskFixed : Math.max((riskPct / 100) * cur, minRisk);
      eq.push(rng() < wr ? cur + risk * winLossRatio : Math.max(0, cur - risk));
    }
    sims.push(eq);
  }
  return sims;
}

function runBootstrapSim(p: {
  startingEquity: number; rMultiples: number[];
  riskFixed: number; riskPct: number; minRisk: number;
  riskMode: 'fixed' | 'percent'; seed: number; numTrades: number;
}): number[][] {
  const { startingEquity, rMultiples, riskFixed, riskPct, minRisk, riskMode, seed, numTrades } = p;
  const rng = mulberry32(seed);
  const sims: number[][] = [];
  const n = rMultiples.length;

  for (let s = 0; s < NUM_SIMULATIONS; s++) {
    const eq: number[] = [startingEquity];
    for (let t = 0; t < numTrades; t++) {
      const cur = eq[eq.length - 1]!;
      if (cur <= 0) { for (let r = t; r < numTrades; r++) eq.push(0); break; }
      const risk = riskMode === 'fixed' ? riskFixed : Math.max((riskPct / 100) * cur, minRisk);
      const rMul = rMultiples[Math.floor(rng() * n)]!;
      eq.push(Math.max(0, cur + rMul * risk));
    }
    sims.push(eq);
  }
  return sims;
}

/* ------------------------------------------------------------------ */
/*  Metrics                                                            */
/* ------------------------------------------------------------------ */

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
  const maxDrawdownPcts: number[] = [];
  const finalEquities: number[] = [];
  let globalMinEquity = Infinity;
  let globalMaxEquity = -Infinity;
  let globalMaxConsWins = 0;
  let globalMaxConsLosses = 0;
  let ruinedCount = 0;

  for (const equity of simulations) {
    let peak = equity[0]!;
    let maxDD = 0;
    let maxDDPct = 0;
    let consWins = 0;
    let consLosses = 0;
    let simMaxConsWins = 0;
    let simMaxConsLosses = 0;
    let hitZero = false;

    for (let i = 1; i < equity.length; i++) {
      const val = equity[i]!;
      const prev = equity[i - 1]!;
      if (val <= 0) hitZero = true;
      if (val > peak) peak = val;
      const dd = peak - val;
      if (dd > maxDD) maxDD = dd;
      if (peak > 0) {
        const ddPct = 1 - val / peak;
        if (ddPct > maxDDPct) maxDDPct = ddPct;
      }
      if (val < globalMinEquity) globalMinEquity = val;
      if (val > globalMaxEquity) globalMaxEquity = val;
      if (val > prev) {
        consWins++; consLosses = 0;
        if (consWins > simMaxConsWins) simMaxConsWins = consWins;
      } else if (val < prev) {
        consLosses++; consWins = 0;
        if (consLosses > simMaxConsLosses) simMaxConsLosses = consLosses;
      }
    }

    if (hitZero) ruinedCount++;
    maxDrawdowns.push(maxDD);
    maxDrawdownPcts.push(maxDDPct);
    finalEquities.push(equity[equity.length - 1]!);
    if (simMaxConsWins > globalMaxConsWins) globalMaxConsWins = simMaxConsWins;
    if (simMaxConsLosses > globalMaxConsLosses) globalMaxConsLosses = simMaxConsLosses;
  }

  const biggestMaxDrawdown = Math.max(...maxDrawdowns);
  const avgMaxDrawdown = maxDrawdowns.reduce((a, b) => a + b, 0) / maxDrawdowns.length;
  const biggestMaxDrawdownPct = Math.max(...maxDrawdownPcts) * 100;
  const avgMaxDrawdownPct = (maxDrawdownPcts.reduce((a, b) => a + b, 0) / maxDrawdownPcts.length) * 100;
  const avgFinalEquity = finalEquities.reduce((a, b) => a + b, 0) / finalEquities.length;
  const avgPerformancePct = startingEquity > 0 ? (avgFinalEquity / startingEquity) * 100 : 0;
  const returnOnMaxDrawdown = biggestMaxDrawdown > 0 ? avgFinalEquity / biggestMaxDrawdown : 0;
  const pctProfitable = (finalEquities.filter((e) => e > startingEquity).length / simulations.length) * 100;
  const pctRuined = (ruinedCount / simulations.length) * 100;

  return {
    kelly, expectation,
    biggestMaxDrawdown, biggestMaxDrawdownPct,
    avgMaxDrawdown, avgMaxDrawdownPct,
    minEquity: globalMinEquity, maxEquity: globalMaxEquity,
    avgFinalEquity, avgPerformancePct, returnOnMaxDrawdown,
    maxConsecutiveWins: globalMaxConsWins,
    maxConsecutiveLosses: globalMaxConsLosses,
    pctProfitable, pctRuined,
  };
}

/* ------------------------------------------------------------------ */
/*  Chart data — limited points and display lines for render perf      */
/* ------------------------------------------------------------------ */

function buildChartData(simulations: number[][], numTrades: number): SimPoint[] {
  const step = Math.max(1, Math.ceil(numTrades / MAX_CHART_POINTS));
  const points: SimPoint[] = [];

  for (let t = 0; t <= numTrades; t += step) {
    const pt: SimPoint = { trade: t, avgEquity: 0 };
    let sum = 0;
    for (let s = 0; s < NUM_SIMULATIONS; s++) {
      const val = simulations[s]![t]!;
      if (s < MAX_DISPLAY_LINES) pt[`sim_${s}`] = val;
      sum += val;
    }
    pt.avgEquity = sum / NUM_SIMULATIONS;
    points.push(pt);
  }

  // Ensure last trade is always included
  const last = points[points.length - 1];
  if (last && last.trade !== numTrades) {
    const pt: SimPoint = { trade: numTrades, avgEquity: 0 };
    let sum = 0;
    for (let s = 0; s < NUM_SIMULATIONS; s++) {
      const val = simulations[s]![numTrades]!;
      if (s < MAX_DISPLAY_LINES) pt[`sim_${s}`] = val;
      sum += val;
    }
    pt.avgEquity = sum / NUM_SIMULATIONS;
    points.push(pt);
  }

  return points;
}

/* ------------------------------------------------------------------ */
/*  Message handler                                                    */
/* ------------------------------------------------------------------ */

self.onmessage = (e: MessageEvent<WorkerParams>) => {
  const { mode, startingEquity, winRate, winLossRatio, riskFixed, riskPct, minRisk, riskMode, rMultiples, seed, numTrades } = e.data;

  const simulations =
    mode === 'bootstrap' && rMultiples.length > 0
      ? runBootstrapSim({ startingEquity, rMultiples, riskFixed, riskPct, minRisk, riskMode, seed, numTrades })
      : runParametricSim({ startingEquity, winRate, winLossRatio, riskFixed, riskPct, minRisk, riskMode, seed, numTrades });

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
  const chartData = buildChartData(simulations, numTrades);

  self.postMessage({ chartData, metrics } as WorkerResult);
};
