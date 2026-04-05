import apiClient from './client';
import type { ClientConfig } from '../types/clientConfig.types';

/** Fetch public app config consumed by frontend upload UIs. */
export async function getClientConfig(): Promise<ClientConfig> {
  const res = await apiClient.get<ClientConfig>('/client-config');
  return res.data;
}
