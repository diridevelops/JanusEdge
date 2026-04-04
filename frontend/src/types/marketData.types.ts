/** OHLC data point from market data API. */
export interface OHLCDataPoint {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

/** Chart interval options. */
export type ChartInterval = '1m' | '5m' | '15m' | '1h' | '1d';

/** Saved market-data day summary returned by the backend. */
export interface SavedMarketDataDay {
  date: string;
  symbol: string;
  raw_symbol: string | null;
  available_timeframes: string[];
  has_ticks: boolean;
  updated_at: string | null;
}

/** Daily summary row returned by the tick-data preview endpoint. */
export interface TickImportTradingDateSummary {
  date: string;
  tick_count: number;
  first_tick_at: string;
  last_tick_at: string;
}

/** Preview payload for a pending NinjaTrader tick-data import. */
export interface TickImportPreview {
  file_name: string;
  symbol_guess: string | null;
  total_lines: number;
  valid_ticks: number;
  skipped_lines: number;
  first_tick_at: string | null;
  last_tick_at: string | null;
  trading_dates: TickImportTradingDateSummary[];
}

/** Progress counters for a tick-data import batch. */
export interface MarketDataImportProgress {
  processed_bytes: number;
  total_bytes: number;
  processed_percentage: number;
}

/** Aggregate stats for a tick-data import batch. */
export interface MarketDataImportStats {
  processed_lines: number;
  valid_ticks: number;
  skipped_lines: number;
  days_completed: number;
  datasets_written: number;
}

/** Status values returned by the tick-data import batch endpoint. */
export type MarketDataImportStatus =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed';

export type MarketDataBatchType = 'preview' | 'import';

/** Market-data import batch returned by the backend. */
export interface MarketDataImportBatch {
  id: string;
  user_id?: string;
  file_name: string;
  file_hash: string;
  file_size_bytes: number;
  source_platform: string;
  batch_type: MarketDataBatchType;
  symbol: string;
  raw_symbol: string | null;
  status: MarketDataImportStatus;
  progress: MarketDataImportProgress;
  stats: MarketDataImportStats;
  error_message: string | null;
  preview: TickImportPreview | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

/** Tag from the API. */
export interface Tag {
  id: string;
  user_id: string;
  name: string;
  color: string;
  created_at: string;
}
