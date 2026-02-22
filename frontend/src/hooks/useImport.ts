import { useState, useCallback } from 'react';
import type {
  ParsedExecution,
  ParseError,
  ReconstructedTrade,
} from '../types/import.types';
import { uploadCSV, reconstructTrades, finalizeImport } from '../api/imports.api';

interface ApiErrorPayload {
  error?: string | { message?: string };
}

interface ApiErrorLike {
  message?: string;
  response?: {
    status?: number;
    data?: ApiErrorPayload;
  };
}

function getApiErrorMessage(
  err: unknown,
  fallback: string,
  duplicateFallback: string
): string {
  const apiError = err as ApiErrorLike;
  const status = apiError?.response?.status;
  const payloadError = apiError?.response?.data?.error;
  const serverMessage =
    typeof payloadError === 'string'
      ? payloadError
      : payloadError?.message;

  if (status === 409) {
    return serverMessage ?? duplicateFallback;
  }

  return (
    serverMessage
    ?? (err instanceof Error ? err.message : undefined)
    ?? fallback
  );
}

/** Import wizard step identifiers. */
export type ImportStep = 'upload' | 'preview' | 'fees' | 'summary';

interface ImportState {
  /** Current wizard step. */
  step: ImportStep;
  /** Whether an async operation is in progress. */
  isLoading: boolean;
  /** Current error message, if any. */
  error: string | null;
  /** Detected platform name. */
  platform: string;
  /** Original file name. */
  fileName: string;
  /** File SHA-256 hash from backend. */
  fileHash: string;
  /** File size in bytes. */
  fileSize: number;
  /** Column mapping from parser. */
  columnMapping: Record<string, string> | null;
  /** Parsed executions from upload. */
  executions: ParsedExecution[];
  /** Parse errors from upload. */
  parseErrors: ParseError[];
  /** Warnings from upload. */
  warnings: string[];
  /** Total rows found in CSV. */
  totalRows: number;
  /** Successfully parsed rows. */
  parsedRows: number;
  /** Reconstructed trades. */
  trades: ReconstructedTrade[];
  /** Fee assignments: trade index → fee amount. */
  fees: Record<number, number>;
  /** Initial risk assignments: trade index → risk amount. */
  initialRisks: Record<number, number>;
  /** Number of finalized trades. */
  finalizedCount: number;
  /** Uploaded files metadata for multi-file import. */
  uploadedFiles: Array<{
    platform: string;
    file_name: string;
    file_hash: string;
    file_size: number;
    column_mapping: Record<string, string> | null;
    executions: ParsedExecution[];
  }>;
  /** Mapping between displayed trade index and source file trade index. */
  tradeOrigins: Array<{ fileIndex: number; tradeIndex: number }>;
}

const INITIAL_STATE: ImportState = {
  step: 'upload',
  isLoading: false,
  error: null,
  platform: '',
  fileName: '',
  fileHash: '',
  fileSize: 0,
  columnMapping: null,
  executions: [],
  parseErrors: [],
  warnings: [],
  totalRows: 0,
  parsedRows: 0,
  trades: [],
  fees: {},
  initialRisks: {},
  finalizedCount: 0,
  uploadedFiles: [],
  tradeOrigins: [],
};

/** Custom hook for the multi-step import wizard state machine. */
export function useImport() {
  const [state, setState] = useState<ImportState>(INITIAL_STATE);

  /** Step 1: Upload and parse one or more CSV files. */
  const handleUpload = useCallback(async (files: File[]) => {
    if (files.length === 0) {
      return;
    }

    setState((prev) => ({
      ...prev,
      isLoading: true,
      error: null,
    }));

    try {
      const results = await Promise.all(
        files.map((file) => uploadCSV(file))
      );

      const allExecutions = results.flatMap((r) => r.executions);
      const allErrors = results.flatMap((r) => r.errors);
      const allWarnings = results.flatMap((r) => r.warnings ?? []);
      const totalRows = results.reduce(
        (sum, r) => sum + (r.total_rows ?? r.row_count ?? 0),
        0
      );
      const parsedRows = results.reduce(
        (sum, r) => sum + (r.parsed_rows ?? r.executions.length),
        0
      );

      const platforms = Array.from(
        new Set(results.map((r) => r.platform))
      );
      const displayPlatform =
        platforms.length === 1
          ? (platforms[0] ?? '')
          : 'Mixed';

      const first = results[0];
      const fileLabel =
        results.length === 1
          ? first?.file_name ?? ''
          : `${results.length} CSV files`;

      setState((prev) => ({
        ...prev,
        isLoading: false,
        step: 'preview',
        platform: displayPlatform,
        fileName: fileLabel,
        fileHash: first?.file_hash ?? '',
        fileSize: first?.file_size ?? 0,
        columnMapping: first?.column_mapping ?? null,
        executions: allExecutions,
        parseErrors: allErrors,
        warnings: allWarnings,
        totalRows,
        parsedRows,
        uploadedFiles: results.map((result) => ({
          platform: result.platform,
          file_name: result.file_name,
          file_hash: result.file_hash,
          file_size: result.file_size,
          column_mapping: result.column_mapping ?? null,
          executions: result.executions,
        })),
      }));
    } catch (err: unknown) {
      const message = getApiErrorMessage(
        err,
        'Upload failed. Please try again.',
        files.length > 1
          ? 'One or more selected files were already imported. Remove duplicate files and try again.'
          : 'This file was already imported. Please choose a different CSV file.'
      );
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
    }
  }, []);

  /** Step 2: Reconstruct trades from parsed executions. */
  const handleReconstruct = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      isLoading: true,
      error: null,
    }));

    try {
      const sourceFiles =
        state.uploadedFiles.length > 0
          ? state.uploadedFiles
          : [
              {
                platform: state.platform,
                file_name: state.fileName,
                file_hash: state.fileHash,
                file_size: state.fileSize,
                column_mapping: state.columnMapping,
                executions: state.executions,
              },
            ];

      const reconstructedByFile = await Promise.all(
        sourceFiles.map((file) =>
          reconstructTrades(file.executions)
        )
      );

      const allTrades: ReconstructedTrade[] = [];
      const tradeOrigins: Array<{
        fileIndex: number;
        tradeIndex: number;
      }> = [];

      reconstructedByFile.forEach((result, fileIndex) => {
        result.trades.forEach((trade, tradeIndex) => {
          allTrades.push(trade);
          tradeOrigins.push({ fileIndex, tradeIndex });
        });
      });

      // Initialize fees from commission data if available
      const initialFees: Record<number, number> = {};
      const initialRisks: Record<number, number> = {};
      allTrades.forEach((trade, idx) => {
        const initialFee = trade.fee ?? 0;
        initialFees[idx] = initialFee;
        const initialNetPnl = trade.gross_pnl - initialFee;
        initialRisks[idx] =
          initialNetPnl < 0
            ? Math.abs(initialNetPnl)
            : 0;
      });

      setState((prev) => ({
        ...prev,
        isLoading: false,
        step: 'fees',
        trades: allTrades,
        fees: initialFees,
        initialRisks,
        tradeOrigins,
      }));
    } catch (err: unknown) {
      const message = getApiErrorMessage(
        err,
        'Trade reconstruction failed.',
        'A duplicate file was detected. Please remove already imported files and try again.'
      );
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
    }
  }, [state.uploadedFiles, state.platform, state.fileName, state.fileHash, state.fileSize, state.columnMapping, state.executions]);

  /** Step 3: Finalize import with fee assignments. */
  const handleFinalize = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      isLoading: true,
      error: null,
    }));

    try {
      const sourceFiles =
        state.uploadedFiles.length > 0
          ? state.uploadedFiles
          : [
              {
                platform: state.platform,
                file_name: state.fileName,
                file_hash: state.fileHash,
                file_size: state.fileSize,
                column_mapping: state.columnMapping,
                executions: state.executions,
              },
            ];

      const originMap =
        state.tradeOrigins.length > 0
          ? state.tradeOrigins
          : state.trades.map((_, idx) => ({
              fileIndex: 0,
              tradeIndex: idx,
            }));

      const finalizeResults: Array<{
        trades_imported: number;
        import_batch_id: string;
      }> = [];

      for (const [fileIndex, file] of sourceFiles.entries()) {
        const tradesPayload = originMap
          .map((origin, globalIndex) => ({
            origin,
            globalIndex,
          }))
          .filter(({ origin }) => origin.fileIndex === fileIndex)
          .map(({ origin, globalIndex }) => ({
            index: origin.tradeIndex,
            fee: state.fees[globalIndex] ?? 0,
            initial_risk:
              state.initialRisks[globalIndex] ?? 0,
          }));

        const result = await finalizeImport({
          file_hash: file.file_hash,
          platform: file.platform,
          file_name: file.file_name,
          file_size: file.file_size,
          reconstruction_method: 'FIFO',
          trades: tradesPayload,
          executions: file.executions,
          column_mapping: file.column_mapping,
        });
        finalizeResults.push(result);
      }

      const totalImported = finalizeResults.reduce(
        (sum, result) => sum + result.trades_imported,
        0
      );

      setState((prev) => ({
        ...prev,
        isLoading: false,
        step: 'summary',
        finalizedCount: totalImported,
      }));
    } catch (err: unknown) {
      const message = getApiErrorMessage(
        err,
        'Import finalization failed.',
        'One or more files were already imported. Please remove duplicates and retry.'
      );
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
    }
  }, [state.tradeOrigins, state.uploadedFiles, state.trades, state.fees, state.initialRisks, state.fileHash, state.platform, state.fileName, state.fileSize, state.executions, state.columnMapping]);

  /** Update fee for a specific trade. */
  const setFee = useCallback((index: number, fee: number) => {
    setState((prev) => ({
      ...prev,
      fees: { ...prev.fees, [index]: fee },
    }));
  }, []);

  /** Apply bulk fee to all trades. */
  const setBulkFee = useCallback((fee: number) => {
    setState((prev) => {
      const newFees: Record<number, number> = {};
      prev.trades.forEach((_, idx) => {
        newFees[idx] = fee;
      });
      return { ...prev, fees: newFees };
    });
  }, []);

  /** Update initial risk for a specific trade. */
  const setInitialRisk = useCallback((index: number, risk: number) => {
    setState((prev) => ({
      ...prev,
      initialRisks: {
        ...prev.initialRisks,
        [index]: Math.max(0, risk),
      },
    }));
  }, []);

  /** Apply bulk initial risk to all trades. */
  const setBulkInitialRisk = useCallback((risk: number) => {
    setState((prev) => {
      const newRisks: Record<number, number> = {};
      prev.trades.forEach((_, idx) => {
        newRisks[idx] = Math.max(0, risk);
      });
      return { ...prev, initialRisks: newRisks };
    });
  }, []);

  /** Go back to a previous step. */
  const goToStep = useCallback((step: ImportStep) => {
    setState((prev) => ({
      ...prev,
      step,
      error: null,
    }));
  }, []);

  /** Reset wizard to initial state. */
  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  return {
    ...state,
    handleUpload,
    handleReconstruct,
    handleFinalize,
    setFee,
    setBulkFee,
    setInitialRisk,
    setBulkInitialRisk,
    goToStep,
    reset,
  };
}
