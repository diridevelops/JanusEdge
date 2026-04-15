/** Types for the What-if stop analysis module. */

export interface ConfidenceInterval {
  lower: number;
  upper: number;
}

export interface StopAnalysisConfidenceIntervals {
  mean?: ConfidenceInterval | null;
  median?: ConfidenceInterval | null;
  p75?: ConfidenceInterval | null;
  p90?: ConfidenceInterval | null;
  p95?: ConfidenceInterval | null;
  iqr?: ConfidenceInterval | null;
}

export interface StopAnalysisDetail {
  trade_id: string;
  symbol: string;
  side: string;
  entry_time: string;
  net_pnl: number;
  overshoot_r: number;
}

export interface StopAnalysisResponse {
  count: number;
  mean: number;
  median: number;
  p75: number;
  p90: number;
  p95: number;
  iqr: number;
  confidence_intervals?: StopAnalysisConfidenceIntervals | null;
  details: StopAnalysisDetail[];
}

export interface WickedOutTrade {
  id: string;
  symbol: string;
  side: string;
  entry_time: string;
  exit_time: string;
  net_pnl: number;
  wish_stop_price: number | null;
  target_price: number | null;
  has_tick_data: boolean;
}

export interface WickedOutTradesResponse {
  trades: WickedOutTrade[];
}

export interface SimulationMetrics {
  total_pnl: number;
  avg_pnl: number;
  win_rate: number;
  total_winners: number;
  total_losers: number;
  profit_factor: number | string;
  expectancy_r: number | null;
}

export interface SimulationDetail {
  trade_id: string;
  symbol: string;
  side: string;
  entry_time: string;
  original_pnl: number;
  new_pnl: number;
  original_r: number | null;
  new_r: number | null;
  change_r: number | null;
  converted: boolean;
  status: string;
  target_source: 'explicit' | 'derived' | null;
}

export interface SimulationResponse {
  original: SimulationMetrics;
  what_if: SimulationMetrics;
  trades_total: number;
  trades_converted: number;
  trades_simulated: number;
  trades_skipped: number;
  details: SimulationDetail[];
}
