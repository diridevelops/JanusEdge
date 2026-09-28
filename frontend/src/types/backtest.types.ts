/** Progress persisted by the Backtest preparation worker. */
export interface BacktestRunProgress {
  stage: string;
  percent: number | null;
}

export interface BacktestInstrumentCatalog {
  instruments: string[];
}

export type BacktestRandomPeriodMonths = 1 | 3 | 6 | 12;
export type BacktestPeriodSelection = 'manual' | 'random';

interface CreateManualBacktestRunRequest {
  instrument: string;
  start_date: string;
  end_date: string;
  display_timezone: string;
}

export type CreateBacktestRunRequest = CreateManualBacktestRunRequest | {
  instrument: string;
  display_timezone: string;
  period_selection: 'random';
  period_months: BacktestRandomPeriodMonths;
};

export type BacktestRunStatus = 'selecting_period' | 'preparing' | 'ready' | 'deleting';
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
  requested_start_date: string | null;
  requested_end_date: string | null;
  display_timezone: string;
  period_selection?: BacktestPeriodSelection;
  period_months?: BacktestRandomPeriodMonths | null;
  status: BacktestRunStatus;
  account_id: string | null;
  account_label: string | null;
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
  context_start_utc_ms: number;
  replay_start_source_index: number;
  replay_start_time_ms: number | null;
  replay_period_candle_count: number;
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

export interface BacktestChartWorkspacePanel {
  id: string;
  type: 'backtest-chart';
  interval_minutes: number;
}

/** FlexLayout tree and chart metadata persisted for one owner/run pair. */
export interface BacktestChartWorkspaceDefinition {
  schema_version: 1;
  layout_engine: 'flexlayout-react';
  id: string;
  name: 'default';
  tree: unknown;
  panels: Record<string, BacktestChartWorkspacePanel>;
}

export interface BacktestChartWorkspaceDocument extends BacktestChartWorkspaceDefinition {
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface BacktestChartWorkspaceResponse {
  workspace: BacktestChartWorkspaceDocument | null;
  revision: number;
  legacy_tabs: BacktestChartTab[];
}

export interface BacktestChartWorkspaceSaveRequest {
  expected_revision: number;
  workspace: BacktestChartWorkspaceDefinition;
}

export interface BacktestRunDetail extends BacktestRunSummary {
  start_utc_ms: number | null;
  end_utc_ms: number | null;
  context_start_utc_ms: number | null;
  coverage: BacktestRunCoverage | null;
  warmup_coverage: BacktestRunCoverage | null;
  snapshot: BacktestSnapshotMetadata | null;
  replay_cursor: BacktestReplayPosition | null;
  tabs: BacktestChartTab[];
}

export interface BacktestPreparationNotice {
  id: string;
  instrument: string;
  requested_start_date: string | null;
  requested_end_date: string | null;
  period_selection?: BacktestPeriodSelection;
  period_months?: BacktestRandomPeriodMonths | null;
  outcome: BacktestPreparationOutcome;
  next_action: BacktestPreparationNextAction;
  message?: string;
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
