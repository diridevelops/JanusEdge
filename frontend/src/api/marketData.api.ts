import apiClient from './client';
import type { OHLCDataPoint } from '../types/marketData.types';

interface OHLCParams {
  symbol: string;
  interval?: string;
  start?: string;
  end?: string;
  raw_symbol?: string;
}

/** Fetch OHLC candle data. */
export async function getOHLC(
  params: OHLCParams
): Promise<OHLCDataPoint[]> {
  const res = await apiClient.get<{ ohlc_data: OHLCDataPoint[] }>(
    '/market-data/ohlc',
    { params }
  );
  return res.data.ohlc_data;
}
