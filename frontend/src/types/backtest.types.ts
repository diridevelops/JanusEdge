/** Progress persisted by the Backtest preparation worker. */
export interface BacktestRunProgress {
  stage: string;
  percent: number | null;
}

export interface BacktestInstrumentCatalog {
  instruments: string[];
}

export interface CreateBacktestRunRequest {
  instrument: string;
  start_date: string;
  end_date: string;
  display_timezone: string;
}

export type BacktestRunStatus = 'preparing' | 'ready';
export type BacktestPreparationOutcome = 'no_data' | 'failed';
export type BacktestPreparationNextAction = 'edit_range' | 'start_new_run';

/** Coverage for the immutable one-minute selection owned by a ready run. */
export interface BacktestRunCoverage {
  first_time_ms: number;
  last_time_ms: number;
  candle_count: number;
  available_utc_dates: string[];
  empty_utc_dates: string[];
  partial_gaps: BacktestPartialGapSummary;
}

export interface BacktestPartialGapSummary {
  gap_count: number;
  missing_minutes: number;
  longest_gap_minutes: number | null;
  examples?: Array<{
    start_time_ms: number;
    end_time_ms: number;
    missing_minutes: number;
  }>;
}

export interface BacktestRunSummary {
  id: string;
  instrument: string;
  requested_start_date: string;
  requested_end_date: string;
  display_timezone: string;
  status: BacktestRunStatus;
  account_id: string;
  account_label: string;
  progress: BacktestRunProgress | null;
  created_at: string;
}

export interface BacktestSnapshotMetadata {
  object_key: string;
  sha256: string;
  source_side: 'COMB';
  price_mode: 'combined_midpoint';
  volume_semantics: 'two_sided_quote_liquidity';
  candle_count: number;
  first_time_ms: number;
  last_time_ms: number;
  available_utc_dates: string[];
  fetched_at: string;
}

export interface BacktestReplayPosition {
  source_candle_index: number;
  time_ms: number;
  revision: number;
}

export interface BacktestChartTab {
  id: string;
  position: number;
  interval_minutes: number;
}

export interface BacktestRunDetail extends BacktestRunSummary {
  start_utc_ms: number;
  end_utc_ms: number;
  coverage: BacktestRunCoverage | null;
  snapshot: BacktestSnapshotMetadata | null;
  replay_cursor: BacktestReplayPosition | null;
  tabs: BacktestChartTab[];
}

export interface BacktestPreparationNotice {
  id: string;
  instrument: string;
  requested_start_date: string;
  requested_end_date: string;
  outcome: BacktestPreparationOutcome;
  next_action: BacktestPreparationNextAction;
  created_at: string;
}

/** One source candle from the immutable UTC snapshot. */
export interface BacktestCandle {
  time_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface BacktestDrawingState {
  interval_minutes: number;
  candlekit_version: string;
  schema_version: number;
  revision: number;
  serialized_state: string | null;
}

export interface BacktestReplayPositionRequest {
  source_candle_index: number;
  time_ms: number;
  expected_revision: number;
}

export interface BacktestSaveDrawingsRequest {
  candlekit_version: string;
  schema_version: number;
  expected_revision: number;
  serialized_state: string;
}
