/** Parsed execution from import upload. */
export interface ParsedExecution {
  symbol: string;
  raw_symbol: string;
  side: string;
  quantity: number;
  price: number;
  commission: number;
  timestamp: string;
  order_id: string | null;
  account: string;
}

/** Parse error for a specific row. */
export interface ParseError {
  row: number;
  field: string;
  issue: string;
}

/** Upload response from POST /api/imports/upload. */
export interface UploadResponse {
  platform: string;
  file_name: string;
  file_hash: string;
  file_size: number;
  executions: ParsedExecution[];
  errors: ParseError[];
  warnings: string[];
  row_count: number;
  column_mapping: Record<string, string> | null;
  /** Alias used in wizard for consistency. */
  total_rows: number;
  parsed_rows: number;
}

/** Reconstructed trade preview. */
export interface ReconstructedTrade {
  symbol: string;
  side: string;
  total_quantity: number;
  avg_entry_price: number;
  avg_exit_price: number;
  gross_pnl: number;
  fee: number;
  net_pnl: number;
  entry_time: string;
  exit_time: string;
  execution_count: number;
  executions: ParsedExecution[];
}

/** Reconstruct response. */
export interface ReconstructResponse {
  trades: ReconstructedTrade[];
}

/** Finalize request payload. */
export interface FinalizeRequest {
  file_hash: string;
  platform: string;
  file_name: string;
  file_size: number;
  reconstruction_method: string;
  trades: {
    index: number;
    fee: number;
  }[];
  executions: ParsedExecution[];
  column_mapping: Record<string, string> | null;
}

/** Import batch metadata. */
export interface ImportBatch {
  id: string;
  file_name: string;
  platform: string;
  status: string;
  total_rows: number;
  parsed_rows: number;
  trade_count: number;
  created_at: string;
}
