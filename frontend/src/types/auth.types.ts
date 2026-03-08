/** User profile returned by the API. */
export interface User {
  id: string;
  username: string;
  timezone: string;
  display_timezone: string;
  starting_equity: number;
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

/** Market data cache restore summary. */
export interface RestoreMarketDataSummary {
  upserted: number;
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
  market_data_cache: RestoreMarketDataSummary;
  settings: RestoreSettingsSummary;
}

/** Restore response payload from the portable backup API. */
export interface RestoreBackupResponse {
  message: string;
  summary: RestoreSummary;
}
