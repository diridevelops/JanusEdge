import axios from 'axios';
import {
  CheckCircle2,
  Database,
  Loader2,
  RefreshCw,
  Upload,
  XCircle,
} from 'lucide-react';
import { startTransition, useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import {
  getTickImportPreviewBatch,
  getSavedMarketDataDays,
  getTickImportBatch,
  startTickImportPreview,
  startTickImport,
} from '../api/marketData.api';
import type { UploadProgress } from '../api/marketData.api';
import { TickDataDropZone } from '../components/market-data/TickDataDropZone';
import { PageHeader } from '../components/ui/PageHeader';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import type {
  MarketDataImportBatch,
  SavedMarketDataDay,
  TickImportPreview,
} from '../types/marketData.types';
import {
  MARKET_DATA_UPLOAD_LIMIT_BYTES,
  MARKET_DATA_UPLOAD_LIMIT_LABEL,
} from '../utils/constants';
import { formatDateTime, formatDateTimeWithTimeZone } from '../utils/formatters';

const POLL_INTERVAL_MS = 1500;
const ACTIVE_BATCH_STATUSES = new Set(['queued', 'processing']);
const MARKET_DATA_FILE_TOO_LARGE_MESSAGE = `Tick-data files must be ${MARKET_DATA_UPLOAD_LIMIT_LABEL} or smaller.`;

function getErrorMessage(error: unknown, fallbackMessage: string): string {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 413) {
      return MARKET_DATA_FILE_TOO_LARGE_MESSAGE;
    }

    const apiMessage =
      error.response?.data?.error?.message ?? error.response?.data?.message;
    if (typeof apiMessage === 'string' && apiMessage.trim()) {
      return apiMessage;
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return fallbackMessage;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  }

  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function statusClasses(status: MarketDataImportBatch['status']): string {
  switch (status) {
    case 'completed':
      return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
    case 'failed':
      return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';
    case 'processing':
      return 'bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300';
    default:
      return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300';
  }
}

function PreviewMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900/40">
      <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">{value}</div>
    </div>
  );
}

/** Dedicated market-data import flow for NinjaTrader tick-data files. */
export function MarketDataImportPage() {
  const { user } = useAuth();
  const { addToast } = useToast();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<TickImportPreview | null>(null);
  const [previewBatch, setPreviewBatch] = useState<MarketDataImportBatch | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [symbolOverride, setSymbolOverride] = useState('');
  const [rawSymbolOverride, setRawSymbolOverride] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [isStartingImport, setIsStartingImport] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [uploadStage, setUploadStage] = useState<'preview' | 'import' | null>(null);
  const [isRefreshingStatus, setIsRefreshingStatus] = useState(false);
  const [batch, setBatch] = useState<MarketDataImportBatch | null>(null);
  const [savedDays, setSavedDays] = useState<SavedMarketDataDay[]>([]);
  const [savedDaysError, setSavedDaysError] = useState<string | null>(null);
  const [isSavedDaysLoading, setIsSavedDaysLoading] = useState(true);

  const pollTimeoutRef = useRef<number | null>(null);
  const previewPollTimeoutRef = useRef<number | null>(null);
  const notifiedBatchStateRef = useRef<string | null>(null);
  const notifiedPreviewStateRef = useRef<string | null>(null);

  const clearPollTimeout = useCallback(() => {
    if (pollTimeoutRef.current !== null) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
  }, []);

  const clearPreviewPollTimeout = useCallback(() => {
    if (previewPollTimeoutRef.current !== null) {
      window.clearTimeout(previewPollTimeoutRef.current);
      previewPollTimeoutRef.current = null;
    }
  }, []);

  function resetImportState() {
    clearPollTimeout();
    clearPreviewPollTimeout();
    notifiedBatchStateRef.current = null;
    notifiedPreviewStateRef.current = null;
    setPreview(null);
    setPreviewBatch(null);
    setBatch(null);
    setPreviewError(null);
    setBatchError(null);
    setSymbolOverride('');
    setRawSymbolOverride('');
    setPreviewLoading(false);
    setUploadStage(null);
    setUploadProgress(null);
  }

  const loadBatch = useCallback(
    async (batchId: string, showRefreshState: boolean = false) => {
      if (showRefreshState) {
        setIsRefreshingStatus(true);
      }

      try {
        const nextBatch = await getTickImportBatch(batchId);
        startTransition(() => {
          setBatch(nextBatch);
          setBatchError(nextBatch.error_message ?? null);
        });
        return nextBatch;
      } catch (error: unknown) {
        const message = getErrorMessage(error, 'Failed to refresh import status.');
        setBatchError(message);
        throw error;
      } finally {
        if (showRefreshState) {
          setIsRefreshingStatus(false);
        }
      }
    },
    []
  );

  const loadSavedDays = useCallback(async () => {
    setIsSavedDaysLoading(true);
    setSavedDaysError(null);

    try {
      const nextSavedDays = await getSavedMarketDataDays();
      startTransition(() => {
        setSavedDays(nextSavedDays);
      });
    } catch (error: unknown) {
      setSavedDaysError(getErrorMessage(error, 'Failed to load saved market-data days.'));
    } finally {
      setIsSavedDaysLoading(false);
    }
  }, []);

  const loadPreviewBatch = useCallback(async (batchId: string) => {
    try {
      const nextBatch = await getTickImportPreviewBatch(batchId);
      startTransition(() => {
        setPreviewBatch(nextBatch);
        if (nextBatch.status === 'completed' && nextBatch.preview) {
          setPreview(nextBatch.preview);
          setPreviewError(null);
          setSymbolOverride(nextBatch.preview.symbol_guess ?? '');
        } else if (nextBatch.status === 'failed') {
          setPreview(null);
          setPreviewError(nextBatch.error_message ?? 'Failed to preview the tick-data file.');
        }
      });
      return nextBatch;
    } catch (error: unknown) {
      setPreviewError(getErrorMessage(error, 'Failed to refresh preview status.'));
      throw error;
    }
  }, []);

  async function handleFileAccepted(file: File) {
    resetImportState();

    if (file.size > MARKET_DATA_UPLOAD_LIMIT_BYTES) {
      setSelectedFile(null);
      setPreviewError(MARKET_DATA_FILE_TOO_LARGE_MESSAGE);
      return;
    }

    setSelectedFile(file);
    setPreviewLoading(true);
    setUploadStage('preview');
    setUploadProgress({
      loadedBytes: 0,
      totalBytes: file.size,
      percent: 0,
    });

    try {
      const createdPreviewBatch = await startTickImportPreview(
        file,
        setUploadProgress
      );
      setPreviewBatch(createdPreviewBatch);
      setUploadProgress(null);
      if (createdPreviewBatch.status === 'completed' && createdPreviewBatch.preview) {
        setPreview(createdPreviewBatch.preview);
        setPreviewError(null);
        setSymbolOverride(createdPreviewBatch.preview.symbol_guess ?? '');
        setPreviewLoading(false);
        setUploadStage(null);
      }
    } catch (error: unknown) {
      setPreviewError(getErrorMessage(error, 'Failed to preview the tick-data file.'));
      setPreviewLoading(false);
      setUploadStage(null);
      setUploadProgress(null);
    }
  }

  function handleFileRejected(message: string) {
    resetImportState();
    setSelectedFile(null);
    setPreviewError(message);
  }

  async function handleStartImport() {
    if (!selectedFile || !preview) {
      return;
    }

    if (selectedFile.size > MARKET_DATA_UPLOAD_LIMIT_BYTES) {
      setBatchError(MARKET_DATA_FILE_TOO_LARGE_MESSAGE);
      return;
    }

    setIsStartingImport(true);
    setBatchError(null);
    notifiedBatchStateRef.current = null;
    setUploadStage('import');
    setUploadProgress({
      loadedBytes: 0,
      totalBytes: selectedFile.size,
      percent: 0,
    });

    try {
      const createdBatch = await startTickImport(
        {
          file: selectedFile,
          symbol: symbolOverride,
          rawSymbol: rawSymbolOverride,
        },
        setUploadProgress
      );
      setBatch(createdBatch);
      addToast('success', 'Market-data import started.');
    } catch (error: unknown) {
      setBatchError(getErrorMessage(error, 'Failed to start the market-data import.'));
    } finally {
      setIsStartingImport(false);
      setUploadStage(null);
      setUploadProgress(null);
    }
  }

  async function handleRefreshStatus() {
    if (!batch) {
      return;
    }

    try {
      await loadBatch(batch.id, true);
    } catch {
      addToast('error', 'Failed to refresh import status.');
    }
  }

  useEffect(() => {
    void loadSavedDays();
  }, [loadSavedDays]);

  useEffect(() => {
    clearPreviewPollTimeout();

    if (!previewBatch || !ACTIVE_BATCH_STATUSES.has(previewBatch.status)) {
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const nextBatch = await loadPreviewBatch(previewBatch.id);
        if (cancelled || !nextBatch) {
          return;
        }

        if (ACTIVE_BATCH_STATUSES.has(nextBatch.status)) {
          previewPollTimeoutRef.current = window.setTimeout(poll, POLL_INTERVAL_MS);
          return;
        }

        setPreviewLoading(false);
        setUploadStage(null);
      } catch {
        if (!cancelled) {
          previewPollTimeoutRef.current = window.setTimeout(poll, POLL_INTERVAL_MS * 2);
        }
      }
    };

    previewPollTimeoutRef.current = window.setTimeout(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearPreviewPollTimeout();
    };
  }, [clearPreviewPollTimeout, loadPreviewBatch, previewBatch]);

  useEffect(() => {
    clearPollTimeout();

    if (!batch || !ACTIVE_BATCH_STATUSES.has(batch.status)) {
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const nextBatch = await loadBatch(batch.id);
        if (cancelled || !nextBatch) {
          return;
        }

        if (ACTIVE_BATCH_STATUSES.has(nextBatch.status)) {
          pollTimeoutRef.current = window.setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        if (!cancelled) {
          pollTimeoutRef.current = window.setTimeout(poll, POLL_INTERVAL_MS * 2);
        }
      }
    };

    pollTimeoutRef.current = window.setTimeout(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearPollTimeout();
    };
  }, [batch, clearPollTimeout, loadBatch]);

  useEffect(() => {
    if (!previewBatch) {
      return;
    }

    const notificationKey = `${previewBatch.id}:${previewBatch.status}`;
    if (notifiedPreviewStateRef.current === notificationKey) {
      return;
    }

    if (previewBatch.status === 'completed' && previewBatch.preview) {
      notifiedPreviewStateRef.current = notificationKey;
      addToast('success', 'Tick-data preview ready.');
    }

    if (previewBatch.status === 'failed') {
      notifiedPreviewStateRef.current = notificationKey;
      addToast('error', previewBatch.error_message ?? 'Tick-data preview failed.');
      setPreviewLoading(false);
      setUploadStage(null);
    }
  }, [addToast, previewBatch]);

  useEffect(() => {
    if (!batch) {
      return;
    }

    const notificationKey = `${batch.id}:${batch.status}`;
    if (notifiedBatchStateRef.current === notificationKey) {
      return;
    }

    if (batch.status === 'completed') {
      notifiedBatchStateRef.current = notificationKey;
      void loadSavedDays();
      addToast('success', 'Market-data import completed.');
    }

    if (batch.status === 'failed') {
      notifiedBatchStateRef.current = notificationKey;
      addToast('error', batch.error_message ?? 'Market-data import failed.');
    }
  }, [addToast, batch, loadSavedDays]);

  useEffect(() => {
    return () => {
      clearPollTimeout();
      clearPreviewPollTimeout();
    };
  }, [clearPollTimeout, clearPreviewPollTimeout]);

  const percentComplete = batch?.progress.processed_percentage ?? 0;
  const totalPreviewDays = preview?.trading_dates.length ?? 0;
  const previewDropzoneProgress =
    previewLoading && previewBatch
      ? {
          loadedBytes: previewBatch.progress.processed_bytes,
          totalBytes: previewBatch.progress.total_bytes,
          percent: previewBatch.progress.processed_percentage,
        }
      : null;
  const dropzoneProgress =
    uploadStage === 'preview'
      ? uploadProgress ?? previewDropzoneProgress
      : uploadStage === 'import'
        ? uploadProgress
        : null;
  const isIndeterminateLoading =
    uploadStage === 'import'
    && !!uploadProgress
    && (uploadProgress.percent ?? 0) >= 100
    && !batch;
  const uploadLabel =
    uploadStage === 'preview'
      ? uploadProgress
        ? (uploadProgress.percent ?? 0) >= 100
          ? 'Preparing preview...'
          : 'Uploading file for preview...'
        : previewBatch && ACTIVE_BATCH_STATUSES.has(previewBatch.status)
          ? 'Generating preview...'
          : 'Preparing preview...'
      : uploadStage === 'import'
        ? isIndeterminateLoading
          ? 'Starting import...'
          : 'Uploading file for import...'
        : undefined;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        icon={Database}
        title="Import Market Data"
        description={`Upload a NinjaTrader tick-data text export up to ${MARKET_DATA_UPLOAD_LIMIT_LABEL}, review the daily summary, and ingest stored candles for charts and analytics.`}
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
        <div className="space-y-6">
          <div className="card p-6">
            <div className="mb-4 space-y-1">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-900 dark:text-gray-100">
                Upload Tick Data
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Supported format: NinjaTrader tick-data .txt exports, up to {MARKET_DATA_UPLOAD_LIMIT_LABEL}. A preview is generated before any data is written.
              </p>
            </div>

            <TickDataDropZone
              onFileAccepted={handleFileAccepted}
              onFileRejected={handleFileRejected}
              isLoading={previewLoading || isStartingImport}
              error={previewError}
              loadingLabel={uploadLabel}
              isIndeterminate={isIndeterminateLoading}
              maxSizeBytes={MARKET_DATA_UPLOAD_LIMIT_BYTES}
              maxSizeLabel={MARKET_DATA_UPLOAD_LIMIT_LABEL}
              uploadProgress={dropzoneProgress}
            />
          </div>

          {preview ? (
            <div className="card p-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-900 dark:text-gray-100">
                    Preview Summary
                  </h2>
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    Review the parsed day ranges before starting the import.
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 lg:min-w-[320px]">
                  <PreviewMetric label="File" value={preview.file_name} />
                  <PreviewMetric
                    label="Detected Symbol"
                    value={preview.symbol_guess ?? 'Unknown'}
                  />
                </div>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <PreviewMetric label="Total Rows" value={preview.total_lines.toLocaleString()} />
                <PreviewMetric label="Valid Ticks" value={preview.valid_ticks.toLocaleString()} />
                <PreviewMetric label="Skipped Rows" value={preview.skipped_lines.toLocaleString()} />
                <PreviewMetric label="Trading Days" value={preview.trading_dates.length.toString()} />
              </div>

              <div className="mt-6 grid gap-4 lg:grid-cols-2">
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Normalized Symbol Override
                  </label>
                  <input
                    type="text"
                    value={symbolOverride}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      setSymbolOverride(event.target.value.toUpperCase());
                    }}
                    className="input-field mt-1"
                    placeholder="MES"
                    disabled={isStartingImport || Boolean(batch && ACTIVE_BATCH_STATUSES.has(batch.status))}
                  />
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Optional. Leave as detected unless you need to correct the stored symbol.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Raw Symbol Override
                  </label>
                  <input
                    type="text"
                    value={rawSymbolOverride}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      setRawSymbolOverride(event.target.value.toUpperCase());
                    }}
                    className="input-field mt-1"
                    placeholder="MES 06-26"
                    disabled={isStartingImport || Boolean(batch && ACTIVE_BATCH_STATUSES.has(batch.status))}
                  />
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Optional. Use this if the filename-derived platform symbol needs to be corrected.
                  </p>
                </div>
              </div>

              <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
                <table className="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-800">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                        Trading Date
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                        Tick Count
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                        First Tick
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                        Last Tick
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                    {preview.trading_dates.map((day) => (
                      <tr key={day.date} className="bg-white dark:bg-gray-800">
                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">
                          {day.date}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300">
                          {day.tick_count.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                          {formatDateTimeWithTimeZone(
                            day.first_tick_at,
                            user?.display_timezone ?? user?.timezone
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                          {formatDateTimeWithTimeZone(
                            day.last_tick_at,
                            user?.display_timezone ?? user?.timezone
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {batch ? (
                <div className="mt-6 rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/40">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-900 dark:text-gray-100">
                        Import Progress
                      </h3>
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Progress is updated automatically while the batch is queued or processing.
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={handleRefreshStatus}
                      disabled={isRefreshingStatus}
                      className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-800 disabled:opacity-50 dark:text-gray-400 dark:hover:text-gray-200"
                    >
                      <RefreshCw className={`h-4 w-4 ${isRefreshingStatus ? 'animate-spin' : ''}`} />
                      Refresh
                    </button>
                  </div>

                  <div className="mt-4 space-y-4">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${statusClasses(batch.status)}`}>
                        {batch.status}
                      </span>
                      <span className="text-sm text-gray-600 dark:text-gray-300">
                        {batch.symbol}
                        {batch.raw_symbol ? ` • ${batch.raw_symbol}` : ''}
                      </span>
                    </div>

                    <div>
                      <div className="mb-2 flex items-center justify-between text-xs font-medium text-gray-500 dark:text-gray-400">
                        <span>{percentComplete.toFixed(2)}%</span>
                        <span>
                          {formatBytes(batch.progress.processed_bytes)} / {formatBytes(batch.progress.total_bytes)}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700">
                        <div
                          className="h-2 rounded-full bg-brand-600 transition-all"
                          style={{ width: `${Math.min(Math.max(percentComplete, 0), 100)}%` }}
                        />
                      </div>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <PreviewMetric label="Processed Lines" value={batch.stats.processed_lines.toLocaleString()} />
                      <PreviewMetric label="Valid Ticks" value={batch.stats.valid_ticks.toLocaleString()} />
                      <PreviewMetric label="Skipped Lines" value={batch.stats.skipped_lines.toLocaleString()} />
                      <PreviewMetric label="Datasets Written" value={batch.stats.datasets_written.toLocaleString()} />
                    </div>

                    <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm dark:border-gray-700 dark:bg-gray-800">
                      <div className="flex items-start gap-3">
                        {batch.status === 'completed' ? (
                          <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-600 dark:text-green-400" />
                        ) : batch.status === 'failed' ? (
                          <XCircle className="mt-0.5 h-5 w-5 text-red-600 dark:text-red-400" />
                        ) : (
                          <Loader2 className="mt-0.5 h-5 w-5 animate-spin text-brand-600" />
                        )}

                        <div className="space-y-1">
                          <p className="font-medium text-gray-900 dark:text-gray-100">
                            {batch.status === 'completed'
                              ? 'Import finished successfully.'
                              : batch.status === 'failed'
                                ? 'Import failed.'
                                : 'Import is still running.'}
                          </p>
                          <p className="text-gray-600 dark:text-gray-300">
                            {batch.status === 'completed'
                              ? `${batch.stats.days_completed} trading day${batch.stats.days_completed === 1 ? '' : 's'} processed${totalPreviewDays > 0 ? ` out of ${totalPreviewDays}` : ''}.`
                              : batch.status === 'failed'
                                ? batch.error_message ?? 'The backend reported a failure while processing the file.'
                                : 'This page polls the batch-status endpoint automatically until the backend reports completion or failure.'}
                          </p>
                        </div>
                      </div>
                    </div>

                    {batchError ? (
                      <div className="rounded-md bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
                        {batchError}
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}

              <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 pt-4 dark:border-gray-700">
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {preview.first_tick_at && preview.last_tick_at ? (
                    <span>
                      Range: {formatDateTimeWithTimeZone(preview.first_tick_at, user?.display_timezone ?? user?.timezone)} to{' '}
                      {formatDateTimeWithTimeZone(preview.last_tick_at, user?.display_timezone ?? user?.timezone)}
                    </span>
                  ) : (
                    <span>Ready to start import.</span>
                  )}
                </div>

                {!batch && batchError ? (
                  <div className="w-full rounded-md bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
                    {batchError}
                  </div>
                ) : null}

                <button
                  type="button"
                  onClick={handleStartImport}
                  disabled={isStartingImport || Boolean(batch && ACTIVE_BATCH_STATUSES.has(batch.status))}
                  className="btn-primary inline-flex items-center gap-2"
                >
                  {isStartingImport ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Starting Import...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4" />
                      Start Import
                    </>
                  )}
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <div className="space-y-6">
          <div className="card p-6">
            <div className="space-y-1">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-900 dark:text-gray-100">
                Saved Days
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Stored market-data sessions already available for charts and analytics.
              </p>
            </div>

            {isSavedDaysLoading ? (
              <div className="mt-4 rounded-lg border border-dashed border-gray-300 px-4 py-8 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
                Loading saved market-data days...
              </div>
            ) : savedDaysError ? (
              <div className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
                {savedDaysError}
              </div>
            ) : savedDays.length === 0 ? (
              <div className="mt-4 rounded-lg border border-dashed border-gray-300 px-4 py-8 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
                No saved market-data days found yet.
              </div>
            ) : (
              <div className="mt-4 overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
                <ul className="divide-y divide-gray-100 dark:divide-gray-700">
                  {savedDays.map((day) => (
                    <li
                      key={`${day.symbol}:${day.date}`}
                      className="flex items-start justify-between gap-4 bg-white px-4 py-3 dark:bg-gray-800"
                    >
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                            {day.date}
                          </span>
                          <span className="text-sm text-gray-700 dark:text-gray-300">
                            {day.symbol}
                          </span>
                          {day.raw_symbol ? (
                            <span className="truncate text-xs text-gray-500 dark:text-gray-400">
                              {day.raw_symbol}
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          Timeframes: {day.available_timeframes.length > 0 ? day.available_timeframes.join(', ') : 'None'}
                          {day.has_ticks ? ' • Ticks available' : ''}
                        </p>
                      </div>

                      <div className="shrink-0 text-right text-xs text-gray-500 dark:text-gray-400">
                        {day.updated_at ? (
                          <span>
                            Updated {formatDateTime(day.updated_at, user?.display_timezone ?? user?.timezone)}
                          </span>
                        ) : (
                          <span>Update time unavailable</span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
