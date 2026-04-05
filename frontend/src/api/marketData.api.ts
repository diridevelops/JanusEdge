import type { AxiosProgressEvent } from 'axios';
import apiClient from './client';
import type {
  MarketDataImportBatch,
  OHLCDataPoint,
  SavedMarketDataDay,
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

export interface UploadProgress {
  loadedBytes: number;
  totalBytes: number | null;
  percent: number | null;
}

type UploadProgressCallback = (
  progress: UploadProgress
) => void;

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

/** Delete one saved market-data day and all of its stored datasets. */
export async function deleteSavedMarketDataDay(
  symbol: string,
  date: string
): Promise<string> {
  const res = await apiClient.delete<{ message: string }>(
    '/market-data/saved-days',
    {
      params: { symbol, date },
    }
  );
  return res.data.message;
}

function buildUploadProgress(
  event: AxiosProgressEvent
): UploadProgress {
  const totalBytes =
    typeof event.total === 'number' ? event.total : null;
  const loadedBytes =
    typeof event.loaded === 'number' ? event.loaded : 0;
  const percent =
    totalBytes && totalBytes > 0
      ? (loadedBytes / totalBytes) * 100
      : null;

  return {
    loadedBytes,
    totalBytes,
    percent,
  };
}

/** Start a background preview for a NinjaTrader tick-data text file. */
export async function startTickImportPreview(
  file: File,
  onUploadProgress?: UploadProgressCallback
): Promise<MarketDataImportBatch> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await apiClient.post<MarketDataImportBatch>(
    '/market-data/tick-imports/preview',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: onUploadProgress
        ? (event) => {
            onUploadProgress(buildUploadProgress(event));
          }
        : undefined,
    }
  );

  return res.data;
}

/** Fetch the latest status for a market-data preview batch. */
export async function getTickImportPreviewBatch(
  batchId: string
): Promise<MarketDataImportBatch> {
  const res = await apiClient.get<MarketDataImportBatch>(
    `/market-data/tick-imports/preview/${batchId}`
  );
  return res.data;
}

/** Start a new NinjaTrader tick-data import batch. */
export async function startTickImport(
  params: StartTickImportParams,
  onUploadProgress?: UploadProgressCallback
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
      onUploadProgress: onUploadProgress
        ? (event) => {
            onUploadProgress(buildUploadProgress(event));
          }
        : undefined,
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
