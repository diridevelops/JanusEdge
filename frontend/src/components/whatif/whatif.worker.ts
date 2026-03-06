/**
 * What-if simulation Web Worker.
 *
 * Computes deltas between original and what-if metrics
 * off the main thread, keeping the UI responsive.
 */

interface SimMetrics {
  total_pnl: number;
  avg_pnl: number;
  win_rate: number;
  total_winners: number;
  total_losers: number;
  profit_factor: number | string;
  expectancy_r: number | null;
}

interface SimDetail {
  trade_id: string;
  symbol: string;
  side: string;
  entry_time: string;
  original_pnl: number;
  new_pnl: number;
  converted: boolean;
  status: string;
}

export interface WorkerInput {
  original: SimMetrics;
  what_if: SimMetrics;
  details: SimDetail[];
  trades_total: number;
  trades_converted: number;
  trades_simulated: number;
  trades_skipped: number;
}

export interface WorkerOutput {
  original: SimMetrics;
  whatIf: SimMetrics;
  delta: {
    total_pnl: number;
    avg_pnl: number;
    win_rate: number;
    expectancy_r: number | null;
    winners_change: number;
    losers_change: number;
    profit_factor_improved: boolean;
  };
  tradesTotal: number;
  tradesConverted: number;
  tradesSimulated: number;
  tradesSkipped: number;
  allDetails: SimDetail[];
  convertedDetails: SimDetail[];
  simulatedDetails: SimDetail[];
  skippedDetails: SimDetail[];
}

self.onmessage = (e: MessageEvent<WorkerInput>) => {
  const { original, what_if, details, trades_total, trades_converted, trades_simulated, trades_skipped } = e.data;

  const origPF = typeof original.profit_factor === 'number' ? original.profit_factor : 0;
  const whatIfPF = typeof what_if.profit_factor === 'number' ? what_if.profit_factor : 0;

  const delta = {
    total_pnl: what_if.total_pnl - original.total_pnl,
    avg_pnl: what_if.avg_pnl - original.avg_pnl,
    win_rate: what_if.win_rate - original.win_rate,
    expectancy_r:
      original.expectancy_r !== null && what_if.expectancy_r !== null
        ? what_if.expectancy_r - original.expectancy_r
        : null,
    winners_change: what_if.total_winners - original.total_winners,
    losers_change: what_if.total_losers - original.total_losers,
    profit_factor_improved: whatIfPF > origPF,
  };

  const convertedDetails = details.filter((d) => d.converted);
  const simulatedDetails = details.filter(
    (d) => d.status === 'simulated' && !d.converted,
  );
  const skippedDetails = details.filter(
    (d) => !d.converted && d.status !== 'simulated' && d.status !== 'winner',
  );

  self.postMessage({
    original,
    whatIf: what_if,
    delta,
    tradesTotal: trades_total,
    tradesConverted: trades_converted,
    tradesSimulated: trades_simulated,
    tradesSkipped: trades_skipped,
    allDetails: details,
    convertedDetails,
    simulatedDetails,
    skippedDetails,
  } as WorkerOutput);
};
