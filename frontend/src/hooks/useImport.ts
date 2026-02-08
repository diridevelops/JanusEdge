import { useState, useCallback } from 'react';
import type {
  ParsedExecution,
  ParseError,
  ReconstructedTrade,
} from '../types/import.types';
import { uploadCSV, reconstructTrades, finalizeImport } from '../api/imports.api';

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
  /** Number of finalized trades. */
  finalizedCount: number;
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
  finalizedCount: 0,
};

/** Custom hook for the multi-step import wizard state machine. */
export function useImport() {
  const [state, setState] = useState<ImportState>(INITIAL_STATE);

  /** Step 1: Upload and parse CSV file. */
  const handleUpload = useCallback(async (file: File) => {
    setState((prev) => ({
      ...prev,
      isLoading: true,
      error: null,
    }));

    try {
      const result = await uploadCSV(file);

      setState((prev) => ({
        ...prev,
        isLoading: false,
        step: 'preview',
        platform: result.platform,
        fileName: result.file_name,
        fileHash: result.file_hash,
        fileSize: result.file_size,
        columnMapping: result.column_mapping ?? null,
        executions: result.executions,
        parseErrors: result.errors,
        warnings: result.warnings ?? [],
        totalRows: result.total_rows,
        parsedRows: result.parsed_rows,
      }));
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : (err as { response?: { data?: { error?: string } } })?.response?.data?.error ??
            'Upload failed. Please try again.';
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
      const result = await reconstructTrades(state.executions);

      // Initialize fees from commission data if available
      const initialFees: Record<number, number> = {};
      result.trades.forEach((trade, idx) => {
        initialFees[idx] = trade.fee ?? 0;
      });

      setState((prev) => ({
        ...prev,
        isLoading: false,
        step: 'fees',
        trades: result.trades,
        fees: initialFees,
      }));
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : (err as { response?: { data?: { error?: string } } })?.response?.data?.error ??
            'Trade reconstruction failed.';
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
    }
  }, [state.executions]);

  /** Step 3: Finalize import with fee assignments. */
  const handleFinalize = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      isLoading: true,
      error: null,
    }));

    try {
      const tradesPayload = state.trades.map((_, idx) => ({
        index: idx,
        fee: state.fees[idx] ?? 0,
      }));

      const result = await finalizeImport({
        file_hash: state.fileHash,
        platform: state.platform,
        file_name: state.fileName,
        file_size: state.fileSize,
        reconstruction_method: 'FIFO',
        trades: tradesPayload,
        executions: state.executions,
        column_mapping: state.columnMapping,
      });

      setState((prev) => ({
        ...prev,
        isLoading: false,
        step: 'summary',
        finalizedCount: result.trades_imported,
      }));
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : (err as { response?: { data?: { error?: string } } })?.response?.data?.error ??
            'Import finalization failed.';
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
    }
  }, [state.trades, state.fees, state.fileHash, state.platform, state.fileName, state.fileSize, state.executions, state.columnMapping]);

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
    goToStep,
    reset,
  };
}
