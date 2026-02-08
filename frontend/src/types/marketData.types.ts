/** OHLC data point from market data API. */
export interface OHLCDataPoint {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

/** Chart interval options. */
export type ChartInterval = '1m' | '5m' | '15m' | '1h' | '1d';

/** Tag from the API. */
export interface Tag {
  id: string;
  user_id: string;
  name: string;
  color: string;
  created_at: string;
}
