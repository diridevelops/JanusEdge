/** Trade document from the API. */
export interface Trade {
  id: string;
  user_id: string;
  trade_account_id: string;
  import_batch_id: string | null;
  symbol: string;
  raw_symbol: string;
  side: 'Long' | 'Short';
  total_quantity: number;
  max_quantity: number;
  instrument_type?: 'futures' | 'forex' | string;
  lot_size?: number | null;
  base_currency?: string | null;
  quote_currency?: string | null;
  pip_size?: number | null;
  price_precision?: number | null;
  contract_size?: number | null;
  pip_value_per_standard_lot?: number | null;
  pips?: number | null;
  native_pnl?: number | null;
  native_pnl_currency?: string | null;
  quote_to_usd_rate?: number | null;
  avg_entry_price: number;
  avg_exit_price: number;
  gross_pnl: number;
  fee: number;
  fee_source: string;
  net_pnl: number;
  initial_risk: number;
  entry_time: string;
  exit_time: string;
  holding_time_seconds: number;
  execution_count: number;
  source: 'imported' | 'manual';
  status: 'open' | 'closed' | 'deleted';
  tag_ids: string[];
  strategy: string | null;
  pre_trade_notes: string | null;
  post_trade_notes: string | null;
  wish_stop_price: number | null;
  target_price: number | null;
  attachments: string[];
  created_at: string;
  updated_at: string;
  market_data_cached?: boolean;
}

/** One point on a trade's running gross P&L series. */
export interface RunningPnLPoint {
  time: string;
  pnl: number;
  native_pnl?: number | null;
}

/** Empty-state reasons for the running P&L endpoint. */
export type RunningPnLEmptyReason =
  | 'missing_tick_data'
  | 'no_ticks_in_trade_window'
  | null;

/** Running P&L response from the trade detail API. */
export interface RunningPnLResponse {
  source: 'ticks';
  point_value?: number;
  usd_multiplier?: number;
  pnl_currency?: string;
  native_pnl_currency?: string;
  quote_to_usd_rate?: number;
  lot_size?: number;
  empty_reason: RunningPnLEmptyReason;
  points: RunningPnLPoint[];
}

/** Payload for creating a manual trade. */
export interface ManualTradeRequest {
  symbol: string;
  side: 'Long' | 'Short';
  total_quantity?: number;
  lot_size?: number;
  quote_to_usd_rate?: number;
  entry_price: number;
  exit_price: number;
  entry_time: string;
  exit_time: string;
  fee?: number;
  initial_risk?: number;
  account?: string;
  tags?: string[];
  notes?: string;
}

/** Payload for updating a trade. */
export interface UpdateTradeRequest {
  fee?: number;
  initial_risk?: number;
  fee_source?: string;
  strategy?: string | null;
  pre_trade_notes?: string | null;
  post_trade_notes?: string | null;
  tag_ids?: string[];
  wish_stop_price?: number | null;
  target_price?: number | null;
}
