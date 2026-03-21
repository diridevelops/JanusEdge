import apiClient from './client';
import type {
  MarketDataImportBatch,
  OHLCDataPoint,
  SavedMarketDataDay,
  TickImportPreview,
} from '../types/marketData.types';

export interface OHLCParams {
  symbol: string;
  interval?: string;
  start?: string;
  end?: string;
  raw_symbol?: string;
  force_refresh?: boolean;
}

export interface StartTickImportParams {
  file: File;
  symbol?: string;
  rawSymbol?: string;
}

/** Fetch OHLC candle data from stored market data. */
export async function getOHLC(
  params: OHLCParams
): Promise<OHLCDataPoint[]> {
  const res = await apiClient.get<{ ohlc_data: OHLCDataPoint[] }>(
    '/market-data/ohlc',
    { params }
  );
  return res.data.ohlc_data;
}

/** Fetch saved market-data day summaries for the import page. */
export async function getSavedMarketDataDays(): Promise<SavedMarketDataDay[]> {
  const res = await apiClient.get<{ saved_days: SavedMarketDataDay[] }>(
    '/market-data/saved-days'
  );
  return res.data.saved_days;
}

/** Preview a NinjaTrader tick-data text file before importing it. */
export async function previewTickImport(file: File): Promise<TickImportPreview> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await apiClient.post<TickImportPreview>(
    '/market-data/tick-imports/preview',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );

  return res.data;
}

/** Start a new NinjaTrader tick-data import batch. */
export async function startTickImport(
  params: StartTickImportParams
): Promise<MarketDataImportBatch> {
  const formData = new FormData();
  formData.append('file', params.file);

  if (params.symbol?.trim()) {
    formData.append('symbol', params.symbol.trim());
  }

  if (params.rawSymbol?.trim()) {
    formData.append('raw_symbol', params.rawSymbol.trim());
  }

  const res = await apiClient.post<MarketDataImportBatch>(
    '/market-data/tick-imports',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );

  return res.data;
}

/** Fetch the latest status for a market-data import batch. */
export async function getTickImportBatch(
  batchId: string
): Promise<MarketDataImportBatch> {
  const res = await apiClient.get<MarketDataImportBatch>(
    `/market-data/tick-imports/${batchId}`
  );
  return res.data;
}
