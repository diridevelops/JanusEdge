import apiClient from './client';
import type {
  UploadResponse,
  ReconstructResponse,
  FinalizeRequest,
  ImportBatch,
  ParsedExecution,
} from '../types/import.types';

/** Upload a CSV file for parsing. */
export async function uploadCSV(
  file: File
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post<UploadResponse>(
    '/imports/upload',
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  );
  return res.data;
}

/** Reconstruct trades from parsed executions. */
export async function reconstructTrades(
  executions: ParsedExecution[],
  method: string = 'FIFO'
): Promise<ReconstructResponse> {
  const res = await apiClient.post<ReconstructResponse>(
    '/imports/reconstruct',
    { executions, method }
  );
  return res.data;
}

/** Finalize import with fee assignments. */
export async function finalizeImport(
  data: FinalizeRequest
): Promise<{ trades_imported: number; import_batch_id: string }> {
  const res = await apiClient.post<{
    trades_imported: number;
    import_batch_id: string;
  }>('/imports/finalize', data);
  return res.data;
}

/** List import batches. */
export async function listBatches(): Promise<ImportBatch[]> {
  const res = await apiClient.get<{ batches: ImportBatch[] }>(
    '/imports/batches'
  );
  return res.data.batches;
}

/** Delete an import batch. */
export async function deleteBatch(
  batchId: string
): Promise<void> {
  await apiClient.delete(`/imports/batches/${batchId}`);
}
