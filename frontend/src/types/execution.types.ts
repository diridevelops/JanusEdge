/** Execution from the API. */
export interface Execution {
  id: string;
  trade_id: string | null;
  user_id: string;
  import_batch_id: string;
  trade_account_id: string;
  symbol: string;
  raw_symbol: string;
  side: 'Buy' | 'Sell';
  quantity: number;
  price: number;
  commission: number;
  timestamp: string;
  order_id: string | null;
  platform: string;
}
