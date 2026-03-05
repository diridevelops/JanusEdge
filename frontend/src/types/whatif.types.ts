/** Types for the What-if stop analysis module. */

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
  ci_lower: number;
  ci_upper: number;
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
  has_ohlc_data: boolean;
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
}

export interface SimulationDetail {
  trade_id: string;
  original_pnl: number;
  new_pnl: number;
  converted: boolean;
  status: string;
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
