/** Progress persisted by the Backtest preparation worker. */
export interface BacktestRunProgress {
  stage: string;
  percent: number | null;
}

export interface BacktestInstrumentCatalog {
  instruments: string[];
}

export interface BacktestInstrumentSpecs {
  spec_version: string;
  instruments: Record<string, import('./auth.types').InstrumentSizingMappingEntry>;
}

export type BacktestRandomPeriodMonths = 1 | 3 | 6 | 12;
export type BacktestPeriodSelection = 'manual' | 'random';

export interface BacktestExecutionCosts {
  total_spread_pips: number;
  slippage_pips: number;
  commission_usd_per_lot_per_side: number;
}

interface CreateBacktestRunOptions {
  initial_balance_usd?: number;
  risk_percent?: number;
  warmup_days?: number;
  execution_costs?: BacktestExecutionCosts;
}

interface CreateManualBacktestRunRequest extends CreateBacktestRunOptions {
  instrument: string;
  start_date: string;
  end_date: string;
  display_timezone: string;
}

export type CreateBacktestRunRequest = CreateManualBacktestRunRequest | (CreateBacktestRunOptions & {
  instrument: string;
  display_timezone: string;
  period_selection: 'random';
  period_months: BacktestRandomPeriodMonths;
  blind_mode?: true;
});

export type BacktestRunStatus =
  | 'selecting_period'
  | 'preparing'
  | 'ready'
  | 'complete'
  | 'deleting';
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
  warmup_days?: number;
  blind_mode?: boolean;
  normalized_reference_price?: number | null;
  status: BacktestRunStatus;
  account_id: string | null;
  account_label: string | null;
  initial_balance_usd?: number;
  current_balance_usd?: number;
  risk_percent?: number;
  execution_costs?: BacktestExecutionCosts;
  instrument_metadata?: {
    supported_for_simulation: boolean;
    reason?: string | null;
    price_precision?: number | null;
    tick_size?: number | null;
    pip_size?: number | null;
    price_unit_label?: string | null;
    contract_size?: number | null;
    base_currency?: string | null;
    quote_currency?: string | null;
    quote_currency_unit_scale?: number | null;
    min_lots?: number | null;
    lot_increment?: number | null;
    spec_version?: string | null;
    spec_source?: string | null;
    conversion_spec?: {
      quote_currency: string;
      quote_currency_unit_scale: number;
      supported: boolean;
      reason?: string | null;
      route: Array<{
        instrument: string;
        direction: 'direct' | 'inverse';
        from_currency: string;
        to_currency: string;
      }>;
    } | null;
    instrument_type?: string | null;
  } | null;
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
  furthest_source_candle_index?: number;
  furthest_time_ms?: number;
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
  blind_mode?: boolean;
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

export type BacktestSimulationStatus = 'ready' | 'complete';
export type BacktestSimulationOrderSide = 'buy' | 'sell';
export type BacktestSimulationPositionSide = 'long' | 'short';
export type BacktestSimulationOrderType = 'market' | 'limit' | 'stop_market';
export type BacktestSimulationOrderStatus = 'pending' | 'filled' | 'cancelled';
export type BacktestSimulationOrderRole =
  | 'entry'
  | 'protective_stop'
  | 'protective_target'
  | 'manual_close';
export type BacktestSimulationOperationState =
  | 'pending'
  | 'cleanup_pending'
  | 'committed'
  | 'rejected';

/** A unique client operation and the run-level optimistic revision it expects. */
export interface BacktestSimulationOperationRequest {
  client_operation_id: string;
  expected_revision: number;
}

/** Change the run's risk budget for orders submitted after this operation. */
export interface BacktestSimulationUpdateRiskRequest
  extends BacktestSimulationOperationRequest {
  risk_percent: number;
}

/** Stable idempotency envelope returned by simulation mutation endpoints. */
export interface BacktestSimulationOperationResponse<TResult = Record<string, unknown>> {
  client_operation_id: string;
  sequence: number;
  state: BacktestSimulationOperationState;
  control_revision: number;
  result: TResult | null;
}

type BacktestSimulationSizingRequest =
  | { auto_size: true; lots?: never }
  | { auto_size: false; lots: number };

type BacktestSimulationEntryShape =
  | { order_type: 'market'; entry_price?: never }
  | { order_type: 'limit'; entry_price: number };

/** Entry request: market/limit shape and auto/manual lot sizing are explicit. */
export type BacktestSimulationSubmitOrderRequest =
  & BacktestSimulationOperationRequest
  & BacktestSimulationSizingRequest
  & BacktestSimulationEntryShape
  & {
    side: BacktestSimulationOrderSide;
    stop_loss: number;
    take_profit: number;
  };

export type BacktestSimulationCancelOrderRequest = BacktestSimulationOperationRequest;
export type BacktestSimulationClosePositionRequest = BacktestSimulationOperationRequest;

/** Change one protection level, or both; omitted levels remain unchanged. */
export type BacktestSimulationModifyProtectionRequest =
  & BacktestSimulationOperationRequest
  & (
    | { stop_loss: number; take_profit?: number }
    | { stop_loss?: number; take_profit: number }
  );

export interface BacktestSimulationAdvanceRequest
  extends BacktestSimulationOperationRequest {
  target_source_index: number;
}

export interface BacktestSimulationRewindRequest
  extends BacktestSimulationOperationRequest {
  source_candle_index: number;
  time_ms: number;
}

export interface BacktestSimulationResetRequest
  extends BacktestSimulationOperationRequest {
  confirmed: true;
}

/** Current committed per-run execution cost revision. */
export interface BacktestSimulationCostProfile {
  revision: number;
  operation_sequence: number;
  total_spread_pips: number;
  slippage_pips: number;
  commission_usd_per_lot_per_side: number;
  updated_at: string;
}

/** Versioned entry or protective order visible at the committed sequence. */
export interface BacktestSimulationOrder {
  order_id: string;
  operation_sequence: number;
  entity_version: number;
  reset_generation: number;
  client_order_id: string;
  role: BacktestSimulationOrderRole;
  order_type: BacktestSimulationOrderType;
  side: BacktestSimulationOrderSide;
  lots: number;
  entry_price: number | null;
  sizing_reference_entry_price: number | null;
  sizing_quote_to_usd_rate: number | null;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  sizing_mode: 'auto' | 'manual' | null;
  risk_percent: number | null;
  risk_budget_usd: number | null;
  projected_risk_usd?: number | null;
  status: BacktestSimulationOrderStatus;
  eligible_source_index: number;
  linked_position_id: string | null;
  oco_group_id: string | null;
  submitted_at: string;
  updated_at: string;
}

/** One immutable Backtest allocation represented as an Execution record. */
export interface BacktestSimulationFill {
  id: string;
  trade_id: string;
  backtest_order_id: string;
  simulated_position_id: string;
  symbol: string;
  raw_symbol: string;
  reset_generation: number;
  simulation_operation_sequence: number;
  source_candle_index: number;
  allocation_index: number;
  time_ms: number;
  timestamp: string;
  side: 'buy' | 'sell' | 'Buy' | 'Sell';
  lots: number;
  quantity: number;
  reference_price: number;
  fill_price: number;
  price: number;
  cost_profile_revision: number;
  spread_cost: number;
  slippage_cost: number;
  commission: number;
  commission_usd: number;
  quote_currency: string;
  native_gross_pnl: number | null;
  usd_gross_pnl: number | null;
  quote_to_usd_rate: number | null;
  entry_exit: 'Entry' | 'Exit' | 'entry' | 'exit';
  order_type: BacktestSimulationOrderType;
}

/** Current version of one protected position; P&L is display-only. */
export interface BacktestSimulationPosition {
  position_id: string;
  simulated_trade_id: string;
  reset_generation: number;
  entity_version: number;
  operation_sequence: number;
  instrument: string;
  side: BacktestSimulationPositionSide;
  status: 'open' | 'closed';
  remaining_lots: number;
  weighted_entry_price: number;
  entry_fill_ids: string[];
  original_stop_loss_price: number;
  original_take_profit_price: number;
  stop_loss_order_id: string | null;
  take_profit_order_id: string | null;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  initial_risk_native: number;
  initial_risk_usd: number;
  entry_quote_to_usd_rate: number;
  realized_partial_native_pnl: number;
  realized_partial_usd_pnl: number;
  applied_spread_cost: number;
  applied_slippage_cost: number;
  applied_commission_usd: number;
  tag_ids: string[];
  unrealized_pnl_usd: number | null;
  opened_at: string;
  updated_at: string;
}

/** Backend's compact, run-scoped Journal summary for a fully closed position. */
export type BacktestClosedTradeSummary = Record<string, unknown>;

/** Complete committed view returned by GET /runs/{run_id}/simulation. */
export interface BacktestSimulationState {
  committed_sequence: number;
  control_revision: number;
  reset_generation: number;
  cursor: BacktestReplayPosition;
  pending_operation: boolean;
  backward_navigation_locked: boolean;
  initial_balance_usd: number;
  risk_percent: number;
  current_balance_usd: number;
  mark_price: number | null;
  current_quote_to_usd_rate: number | null;
  cost_profile: BacktestSimulationCostProfile;
  orders: BacktestSimulationOrder[];
  fills: BacktestSimulationFill[];
  positions: BacktestSimulationPosition[];
  closed_trades: BacktestClosedTradeSummary[];
  status: BacktestSimulationStatus;
}
