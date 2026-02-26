/** Summary metrics from GET /api/analytics/summary. */
export interface AnalyticsSummary {
  total_trades: number;
  winners: number;
  losers: number;
  breakeven: number;
  win_rate: number;
  total_gross_pnl: number;
  total_net_pnl: number;
  total_fees: number;
  avg_winner: number;
  avg_loser: number;
  largest_win: number;
  largest_loss: number;
  profit_factor: number | null;
  expectancy: number;
  expectancy_r: number | null;
  wl_ratio_r: number | null;
  avg_holding_time_seconds: number;
  avg_executions: number;
  appt: number;
  pl_ratio: number | null;
  win_per_share_avg: number;
  win_per_share_high: number;
  loss_per_share_avg: number;
  loss_per_share_high: number;
}

/** Single point on the daily equity curve. */
export interface EquityCurvePoint {
  date: string;
  daily_pnl: number;
  cumulative_pnl: number;
  trade_count: number;
  winners: number;
  appt: number;
  win_rate: number;
}

/** Single point on the drawdown series. */
export interface DrawdownPoint {
  date: string;
  cumulative_pnl: number;
  drawdown: number;
  drawdown_pct: number;
}

/** Calendar heatmap day entry. */
export interface CalendarDay {
  date: string;
  net_pnl: number;
  gross_pnl: number;
  trade_count: number;
}

/** P&L distribution bucket. */
export interface DistributionBucket {
  bucket: number;
  count: number;
}

/** Performance grouped by hour of day. */
export interface TimeOfDayEntry {
  hour: number;
  trade_count: number;
  net_pnl: number;
  avg_pnl: number;
  win_rate: number;
}

/** Per-tag analytics. */
export interface TagAnalytics {
  tag_id: string;
  tag_name: string;
  trade_count: number;
  net_pnl: number;
  avg_pnl: number;
  win_rate: number;
  profit_factor: number | null;
}

/** APPT grouped by day of week. */
export interface ApptByDayOfWeekEntry {
  day_of_week: string;
  appt: number;
  trade_count: number;
  net_pnl: number;
}

/** APPT grouped by 15-minute timeframe bucket. */
export interface ApptByTimeframeEntry {
  timespan_start: string;
  appt: number;
  trade_count: number;
  net_pnl: number;
}

/** Running/rolling metrics after each trade. */
export interface EvolutionPoint {
  trade_index: number;
  entry_time: string | null;
  exit_time: string | null;
  net_pnl: number;
  initial_risk: number;
  r_multiple: number | null;
  included_r_count: number;
  running_mean_r: number | null;
  running_mean_r_ci_low: number | null;
  running_mean_r_ci_high: number | null;
  rolling_mean_r: number | null;
  rolling_mean_r_ci_low: number | null;
  rolling_mean_r_ci_high: number | null;
  rolling_r_count: number;
  window: number;
  cum_r: number;
  cum_net_pnl: number;
  appt_running: number;
  rolling_pl_ratio_trade: number | null;
  rolling_pl_ratio_stable: boolean;
  rolling_window_wins: number;
  rolling_window_losses: number;
  running_r_win_rate: number | null;
  running_r_avg_win: number | null;
  running_r_avg_loss_abs: number | null;
}

/** Per-trade P&L for bootstrap resampling. */
export interface TradePnl {
  net_pnl: number;
  /** R-multiple (net_pnl / initial_risk). null when no initial risk. */
  r_multiple: number | null;
}
