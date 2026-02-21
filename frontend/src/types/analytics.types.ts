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
