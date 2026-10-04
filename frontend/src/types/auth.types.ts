/** A symbol mapping entry keyed by normalized base symbol. */
export interface SymbolMappingEntry {
  dollar_value_per_point: number;
}

/** A configured CFD contract used for simulated-trade sizing and P&L. */
export interface InstrumentSizingMappingEntry {
  base_currency: string;
  quote_currency: string;
  quote_currency_unit_scale?: number | null;
  pip_size?: number | null;
  tick_size?: number | null;
  price_precision?: number | null;
  contract_size?: number | null;
  min_lots?: number | null;
  lot_increment?: number | null;
  supported_for_simulation?: boolean;
  reason?: string | null;
  spec_source?: string | null;
  catalog_group?: string | null;
}

/** Instrument sizing rules keyed by exact Dukascopy catalog symbol. */
export type InstrumentSizingMappings = Record<string, InstrumentSizingMappingEntry>;

/** Legacy Forex mapping shape retained for manual trade-entry compatibility. */
export interface ForexSymbolMappingEntry extends InstrumentSizingMappingEntry {
  pip_size: number;
  price_precision: number;
  contract_size: number;
}
export type ForexSymbolMappings = Record<string, ForexSymbolMappingEntry>;

/**
 * User symbol mappings.
 *
 * Legacy futures mappings remain top-level. CFDs use the `instruments` table;
 * legacy Forex mappings remain under `forex` for existing manual trades.
 */
export interface SymbolMappings {
  [symbol: string]: SymbolMappingEntry | InstrumentSizingMappings | undefined;
  forex?: ForexSymbolMappings;
  instruments?: InstrumentSizingMappings;
}

/** User market-data mappings keyed by source symbol. */
export type MarketDataMappings = Record<string, string>;

/** User profile returned by the API. */
export interface User {
  id: string;
  username: string;
  timezone: string;
  display_timezone: string;
  starting_equity: number;
  risk_breakeven_enabled: boolean;
  risk_breakeven_r_threshold: number;
  symbol_mappings: SymbolMappings;
  market_data_mappings: MarketDataMappings;
  created_at: string;
}

/** Login request payload. */
export interface LoginRequest {
  username: string;
  password: string;
}

/** Register request payload. */
export interface RegisterRequest {
  username: string;
  password: string;
  timezone: string;
}

/** Auth response from login/register. */
export interface AuthResponse {
  token: string;
  user: User;
}

/** Downloadable export payload metadata. */
export interface ExportBackupFile {
  blob: Blob;
  filename: string;
}

/** Entity restore counts returned after a backup restore. */
export interface RestoreCountSummary {
  created: number;
  reused: number;
}

/** Trade and execution duplicate-aware restore counts. */
export interface RestoreDuplicateSummary {
  created: number;
  skipped: number;
}

/** Market data restore summary. */
export interface RestoreMarketDataSummary {
  upserted: number;
  objects_restored?: number;
}

/** User settings updated during restore. */
export interface RestoreSettingsSummary {
  updated: string[];
}

/** Aggregate restore summary returned by the backend. */
export interface RestoreSummary {
  accounts: RestoreCountSummary;
  tags: RestoreCountSummary;
  import_batches: RestoreCountSummary;
  trades: RestoreDuplicateSummary;
  executions: RestoreDuplicateSummary;
  media: RestoreDuplicateSummary;
  backtest_runs: RestoreCountSummary;
  market_data_datasets?: RestoreMarketDataSummary;
  market_data_cache?: RestoreMarketDataSummary;
  settings: RestoreSettingsSummary;
}

/** Restore response payload from the portable backup API. */
export interface RestoreBackupResponse {
  message: string;
  summary: RestoreSummary;
}
