import { useCallback, useEffect, useRef, useState } from 'react';
import {
  advanceBacktestSimulation,
  cancelBacktestSimulationOrder,
  closeBacktestSimulationPosition,
  getBacktestSimulationState,
  modifyBacktestSimulationProtection,
  resetBacktestSimulation,
  rewindBacktestSimulation,
  submitBacktestSimulationOrder,
} from '../api/backtests.api';
import type {
  BacktestSimulationAdvanceRequest,
  BacktestSimulationCancelOrderRequest,
  BacktestSimulationClosePositionRequest,
  BacktestSimulationModifyProtectionRequest,
  BacktestSimulationOperationRequest,
  BacktestSimulationOperationResponse,
  BacktestSimulationResetRequest,
  BacktestSimulationRewindRequest,
  BacktestSimulationState,
  BacktestSimulationSubmitOrderRequest,
} from '../types/backtest.types';

export type BacktestSimulationLoadStatus = 'idle' | 'loading' | 'ready' | 'error';

function errorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null) {
    const candidate = error as {
      message?: unknown;
      response?: { data?: { message?: unknown; error?: unknown } };
    };
    const responseMessage = candidate.response?.data?.message;
    if (typeof responseMessage === 'string' && responseMessage) {
      return responseMessage;
    }
    const responseError = candidate.response?.data?.error;
    if (typeof responseError === 'string' && responseError) {
      return responseError;
    }
    if (typeof candidate.message === 'string' && candidate.message) {
      return candidate.message;
    }
  }
  return 'The Backtest simulation request failed.';
}

/** Build the idempotency/revision fields required by every simulation command. */
export function createBacktestSimulationOperationRequest(
  expectedRevision: number
): BacktestSimulationOperationRequest {
  const operationId = typeof crypto !== 'undefined'
    && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `op-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return {
    client_operation_id: operationId,
    expected_revision: expectedRevision,
  };
}

export interface UseBacktestSimulationResult {
  state: BacktestSimulationState | null;
  status: BacktestSimulationLoadStatus;
  error: string | null;
  isRefreshing: boolean;
  isMutating: boolean;
  refresh: () => Promise<BacktestSimulationState | null>;
  submitOrder: (
    request: BacktestSimulationSubmitOrderRequest
  ) => Promise<BacktestSimulationOperationResponse>;
  cancelOrder: (
    orderId: string,
    request: BacktestSimulationCancelOrderRequest
  ) => Promise<BacktestSimulationOperationResponse>;
  closePosition: (
    positionId: string,
    request: BacktestSimulationClosePositionRequest
  ) => Promise<BacktestSimulationOperationResponse>;
  modifyProtection: (
    positionId: string,
    request: BacktestSimulationModifyProtectionRequest
  ) => Promise<BacktestSimulationOperationResponse>;
  advance: (
    request: BacktestSimulationAdvanceRequest
  ) => Promise<BacktestSimulationOperationResponse>;
  rewind: (
    request: BacktestSimulationRewindRequest
  ) => Promise<BacktestSimulationOperationResponse>;
  reset: (
    request: BacktestSimulationResetRequest
  ) => Promise<BacktestSimulationOperationResponse>;
}

/**
 * Load committed simulation state and expose run-scoped mutation commands.
 * Each successful command refreshes state so cursor, revision, and entities
 * reflect the server's committed operation sequence.
 */
export function useBacktestSimulation(
  runId: string,
  enabled = true
): UseBacktestSimulationResult {
  const [state, setState] = useState<BacktestSimulationState | null>(null);
  const [status, setStatus] = useState<BacktestSimulationLoadStatus>(
    enabled && runId ? 'loading' : 'idle'
  );
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [mutationCount, setMutationCount] = useState(0);
  const requestGeneration = useRef(0);
  const runIdRef = useRef(runId);
  const enabledRef = useRef(enabled);
  const mountedRef = useRef(false);
  runIdRef.current = runId;
  enabledRef.current = enabled;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestGeneration.current += 1;
    };
  }, []);

  useEffect(() => {
    const generation = ++requestGeneration.current;
    let active = true;
    setState(null);
    setError(null);
    setIsRefreshing(false);
    setMutationCount(0);
    setStatus(enabled && runId ? 'loading' : 'idle');

    if (!enabled || !runId) {
      return () => {
        active = false;
      };
    }

    void getBacktestSimulationState(runId)
      .then((simulation) => {
        if (!active || generation !== requestGeneration.current) return;
        setState(simulation);
        setStatus('ready');
      })
      .catch((requestError: unknown) => {
        if (!active || generation !== requestGeneration.current) return;
        setError(errorMessage(requestError));
        setStatus('error');
      });

    return () => {
      active = false;
    };
  }, [enabled, runId]);

  const refresh = useCallback(async (): Promise<BacktestSimulationState | null> => {
    if (!enabled || !runId) return null;
    const generation = ++requestGeneration.current;
    setIsRefreshing(true);
    setError(null);
    try {
      const simulation = await getBacktestSimulationState(runId);
      if (
        mountedRef.current
        && generation === requestGeneration.current
        && runIdRef.current === runId
        && enabledRef.current
      ) {
        setState(simulation);
        setStatus('ready');
      }
      return simulation;
    } catch (requestError) {
      if (
        mountedRef.current
        && generation === requestGeneration.current
        && runIdRef.current === runId
        && enabledRef.current
      ) {
        setError(errorMessage(requestError));
        setStatus((current) => current === 'ready' ? current : 'error');
      }
      return null;
    } finally {
      if (
        mountedRef.current
        && generation === requestGeneration.current
        && runIdRef.current === runId
      ) {
        setIsRefreshing(false);
      }
    }
  }, [enabled, runId]);

  const runMutation = useCallback(async <T,>(
    action: () => Promise<T>
  ): Promise<T> => {
    if (!enabled || !runId) {
      throw new Error('A ready Backtest run is required for simulation actions.');
    }
    setMutationCount((count) => count + 1);
    setError(null);
    try {
      const result = await action();
      if (runIdRef.current === runId && enabledRef.current) {
        await refresh();
      }
      if (
        typeof result === 'object'
        && result !== null
        && 'state' in result
        && (result as { state?: unknown }).state === 'rejected'
      ) {
        const operation = result as { result?: { message?: unknown } | null };
        const rejection = operation.result?.message;
        throw new Error(typeof rejection === 'string' && rejection
          ? rejection
          : 'The simulation operation was rejected.');
      }
      return result;
    } catch (requestError) {
      if (runIdRef.current === runId && enabledRef.current) {
        setError(errorMessage(requestError));
      }
      throw requestError;
    } finally {
      if (mountedRef.current) {
        setMutationCount((count) => Math.max(0, count - 1));
      }
    }
  }, [enabled, refresh, runId]);

  const submitOrder = useCallback(
    (request: BacktestSimulationSubmitOrderRequest) => runMutation(
      () => submitBacktestSimulationOrder(runId, request)
    ),
    [runId, runMutation]
  );

  const cancelOrder = useCallback(
    (orderId: string, request: BacktestSimulationCancelOrderRequest) => runMutation(
      () => cancelBacktestSimulationOrder(runId, orderId, request)
    ),
    [runId, runMutation]
  );

  const closePosition = useCallback(
    (positionId: string, request: BacktestSimulationClosePositionRequest) => runMutation(
      () => closeBacktestSimulationPosition(runId, positionId, request)
    ),
    [runId, runMutation]
  );

  const modifyProtection = useCallback(
    (positionId: string, request: BacktestSimulationModifyProtectionRequest) => runMutation(
      () => modifyBacktestSimulationProtection(runId, positionId, request)
    ),
    [runId, runMutation]
  );

  const advance = useCallback(
    (request: BacktestSimulationAdvanceRequest) => runMutation(
      () => advanceBacktestSimulation(runId, request)
    ),
    [runId, runMutation]
  );

  const reset = useCallback(
    (request: BacktestSimulationResetRequest) => runMutation(
      () => resetBacktestSimulation(runId, request)
    ),
    [runId, runMutation]
  );

  const rewind = useCallback(
    (request: BacktestSimulationRewindRequest) => runMutation(
      () => rewindBacktestSimulation(runId, request)
    ),
    [runId, runMutation]
  );

  return {
    state,
    status,
    error,
    isRefreshing,
    isMutating: mutationCount > 0,
    refresh,
    submitOrder,
    cancelOrder,
    closePosition,
    modifyProtection,
    advance,
    rewind,
    reset,
  };
}
