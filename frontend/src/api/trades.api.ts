import apiClient from './client';
import type { Trade, ManualTradeRequest, UpdateTradeRequest } from '../types/trade.types';
import type { PaginatedResponse } from '../types/common.types';

interface TradeListParams {
  page?: number;
  per_page?: number;
  sort_by?: string;
  sort_dir?: string;
  symbol?: string;
  side?: string;
  account?: string;
  tag?: string;
  date_from?: string;
  date_to?: string;
}

/** List trades with pagination and filters. */
export async function listTrades(
  params: TradeListParams = {}
): Promise<PaginatedResponse<Trade>> {
  const res = await apiClient.get<PaginatedResponse<Trade>>('/trades', {
    params,
  });
  return res.data;
}

/** Get a single trade by ID (includes executions). */
export async function getTrade(
  id: string
): Promise<{ trade: Trade; executions: unknown[] }> {
  const res = await apiClient.get<{ trade: Trade; executions: unknown[] }>(
    `/trades/${id}`
  );
  return res.data;
}

/** Create a manual trade. */
export async function createManualTrade(
  data: ManualTradeRequest
): Promise<Trade> {
  const res = await apiClient.post<{ trade: Trade }>('/trades', data);
  return res.data.trade;
}

/** Update a trade. */
export async function updateTrade(
  id: string,
  data: UpdateTradeRequest
): Promise<Trade> {
  const res = await apiClient.put<{ trade: Trade }>(`/trades/${id}`, data);
  return res.data.trade;
}

/** Soft-delete a trade. */
export async function deleteTrade(id: string): Promise<void> {
  await apiClient.delete(`/trades/${id}`);
}

/** Restore a soft-deleted trade. */
export async function restoreTrade(id: string): Promise<void> {
  await apiClient.post(`/trades/${id}/restore`);
}

/** Search trades by text. */
export async function searchTrades(
  query: string
): Promise<Trade[]> {
  const res = await apiClient.get<{ trades: Trade[] }>('/trades/search', {
    params: { q: query },
  });
  return res.data.trades;
}
