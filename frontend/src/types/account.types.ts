/** Trade account from the API. */
export interface TradeAccount {
  id: string;
  user_id: string;
  account_name: string;
  display_name: string;
  source_platform: string;
  is_active: boolean;
  created_at: string;
  /** Missing workspace_mode identifies legacy Real accounts. */
  workspace_mode?: 'real' | 'backtest';
  /** Present for Backtest accounts and identifies the associated replay run. */
  backtest_run_id?: string;
}
