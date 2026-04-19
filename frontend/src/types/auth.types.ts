/** A symbol mapping entry keyed by normalized base symbol. */
export interface SymbolMappingEntry {
  dollar_value_per_point: number;
}

/** User symbol mappings keyed by normalized base symbol. */
export type SymbolMappings = Record<string, SymbolMappingEntry>;

/** User market-data mappings keyed by source symbol. */
export type MarketDataMappings = Record<string, string>;

/** User profile returned by the API. */
export interface User {
  id: string;
  username: string;
  timezone: string;
  display_timezone: string;
  starting_equity: number;
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
  market_data_datasets?: RestoreMarketDataSummary;
  market_data_cache?: RestoreMarketDataSummary;
  settings: RestoreSettingsSummary;
}

/** Restore response payload from the portable backup API. */
export interface RestoreBackupResponse {
  message: string;
  summary: RestoreSummary;
}
