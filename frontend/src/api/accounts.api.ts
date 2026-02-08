import apiClient from './client';
import type { TradeAccount } from '../types/account.types';

/** List all trade accounts. */
export async function listAccounts(): Promise<TradeAccount[]> {
  const res = await apiClient.get<{ accounts: TradeAccount[] }>('/accounts');
  return res.data.accounts;
}

/** Update a trade account. */
export async function updateAccount(
  id: string,
  data: Partial<TradeAccount>
): Promise<TradeAccount> {
  const res = await apiClient.put<TradeAccount>(
    `/accounts/${id}`,
    data
  );
  return res.data;
}
