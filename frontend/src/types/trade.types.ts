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

/** Payload for creating a manual trade. */
export interface ManualTradeRequest {
  symbol: string;
  side: 'Long' | 'Short';
  total_quantity: number;
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
