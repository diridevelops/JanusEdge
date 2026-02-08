/** Trade account from the API. */
export interface TradeAccount {
  id: string;
  user_id: string;
  account_name: string;
  display_name: string;
  source_platform: string;
  is_active: boolean;
  created_at: string;
}
