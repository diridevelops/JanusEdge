import apiClient from './client';
import type { Execution } from '../types/execution.types';
import type { PaginatedResponse } from '../types/common.types';

interface ExecutionListParams {
  trade_id?: string;
  page?: number;
  per_page?: number;
}

/** List executions with optional trade filter. */
export async function listExecutions(
  params: ExecutionListParams = {}
): Promise<PaginatedResponse<Execution>> {
  const res = await apiClient.get<PaginatedResponse<Execution>>(
    '/executions',
    { params }
  );
  return res.data;
}

/** Get a single execution by ID. */
export async function getExecution(
  id: string
): Promise<Execution> {
  const res = await apiClient.get<{ execution: Execution }>(
    `/executions/${id}`
  );
  return res.data.execution;
}
