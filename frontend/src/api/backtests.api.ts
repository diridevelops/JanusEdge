import apiClient from './client';
import type {
  BacktestCandle,
  BacktestChartWorkspaceResponse,
  BacktestChartWorkspaceSaveRequest,
  BacktestDrawingState,
  BacktestInstrumentCatalog,
  BacktestInstrumentSpecs,
  BacktestPreparationNotice,
  BacktestReplayPosition,
  BacktestReplayPositionRequest,
  BacktestRunDetail,
  BacktestRunSummary,
  BacktestSaveDrawingsRequest,
  BacktestSimulationAdvanceRequest,
  BacktestSimulationCancelOrderRequest,
  BacktestSimulationClosePositionRequest,
  BacktestSimulationModifyProtectionRequest,
  BacktestSimulationOperationResponse,
  BacktestSimulationResetRequest,
  BacktestSimulationRewindRequest,
  BacktestSimulationState,
  BacktestSimulationSubmitOrderRequest,
  BacktestSimulationUpdateRiskRequest,
  CreateBacktestRunRequest,
} from '../types/backtest.types';

/** Load the current supported-instrument catalog from the downloader. */
export async function getBacktestInstruments(): Promise<string[]> {
  const response = await apiClient.get<BacktestInstrumentCatalog>(
    '/backtest/instruments'
  );
  return response.data.instruments;
}

/** Create a run and enqueue preparation without waiting for its download. */
export async function createBacktestRun(
  request: CreateBacktestRunRequest
): Promise<BacktestRunSummary> {
  const response = await apiClient.post<{ run: BacktestRunSummary }>(
    '/backtest/runs',
    request
  );
  return response.data.run;
}

/** Fetch the user's selecting, preparing, ready, and deleting runs. */
export async function listBacktestRuns(): Promise<BacktestRunSummary[]> {
  const response = await apiClient.get<{ runs: BacktestRunSummary[] }>(
    '/backtest/runs'
  );
  return response.data.runs;
}

/** Start permanent deletion; HTTP 202 means cleanup is pending, not complete. */
export async function deleteBacktestRun(runId: string): Promise<void> {
  await apiClient.delete(`/backtest/runs/${encodeURIComponent(runId)}`);
}

/** Fetch one owned run and its ready-state replay configuration. */
export async function getBacktestRun(
  runId: string
): Promise<BacktestRunDetail> {
  const response = await apiClient.get<{ run: BacktestRunDetail }>(
    `/backtest/runs/${encodeURIComponent(runId)}`
  );
  return response.data.run;
}

/** Requeue an interrupted run's existing preparation job. */
export async function retryBacktestRun(
  runId: string
): Promise<BacktestRunSummary> {
  const response = await apiClient.post<{ run: BacktestRunSummary }>(
    `/backtest/runs/${encodeURIComponent(runId)}/retry`
  );
  return response.data.run;
}

/** Read result notices that remain after a failed/no-data run is removed. */
export async function listBacktestNotices(): Promise<BacktestPreparationNotice[]> {
  const response = await apiClient.get<{
    notices: BacktestPreparationNotice[];
  }>('/backtest/notices');
  return response.data.notices;
}

/** Dismiss one owned preparation result notice. */
export async function dismissBacktestNotice(
  noticeId: string
): Promise<void> {
  await apiClient.delete(
    `/backtest/notices/${encodeURIComponent(noticeId)}`
  );
}

/** List UTC dates with data in a run's immutable snapshot. */
export async function listBacktestCandleDates(
  runId: string,
  params: { before?: string; after?: string } = {}
): Promise<string[]> {
  const response = await apiClient.get<{ dates: string[] }>(
    `/backtest/runs/${encodeURIComponent(runId)}/candle-dates`,
    { params }
  );
  return response.data.dates;
}

/** Fetch one UTC day of source candles from a run snapshot. */
export async function getBacktestCandlesForDate(
  runId: string,
  date: string
): Promise<BacktestCandle[]> {
  const response = await apiClient.get<{ candles: BacktestCandle[] }>(
    `/backtest/runs/${encodeURIComponent(runId)}/candles`,
    { params: { date } }
  );
  return response.data.candles;
}

/** Fetch interval candles from an owned run's immutable snapshot. */
export async function getBacktestChartCandles(
  runId: string,
  params: { start: string; end: string; interval: '1m' | '5m' | '15m' | '1h' }
): Promise<BacktestCandle[]> {
  const response = await apiClient.get<{ candles: BacktestCandle[] }>(
    `/backtest/runs/${encodeURIComponent(runId)}/chart-candles`,
    { params }
  );
  return response.data.candles;
}

/** Persist a cursor choice with an optimistic revision check. */
export async function saveBacktestReplayPosition(
  runId: string,
  position: BacktestReplayPositionRequest
): Promise<BacktestReplayPosition> {
  const response = await apiClient.put<{ replay_cursor: BacktestReplayPosition }>(
    `/backtest/runs/${encodeURIComponent(runId)}/replay-position`,
    position
  );
  return response.data.replay_cursor;
}

/** Load the saved dock layout or read-only flat tabs awaiting migration. */
export async function getBacktestChartWorkspace(
  runId: string
): Promise<BacktestChartWorkspaceResponse> {
  const response = await apiClient.get<BacktestChartWorkspaceResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/chart-workspace`
  );
  return response.data;
}

/** Compare-and-swap the complete saved dock layout. */
export async function saveBacktestChartWorkspace(
  runId: string,
  request: BacktestChartWorkspaceSaveRequest
): Promise<BacktestChartWorkspaceResponse> {
  const response = await apiClient.put<BacktestChartWorkspaceResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/chart-workspace`,
    request
  );
  return response.data;
}

/** Load authenticated drawing state for one run and interval. */
export async function getBacktestDrawingState(
  runId: string,
  intervalMinutes: number
): Promise<BacktestDrawingState> {
  const response = await apiClient.get<BacktestDrawingState>(
    `/backtest/runs/${encodeURIComponent(runId)}/drawings`,
    { params: { interval_minutes: intervalMinutes } }
  );
  return response.data;
}

/** Save exported CandleKit drawing state with an optimistic revision check. */
export async function saveBacktestDrawingState(
  runId: string,
  intervalMinutes: number,
  drawingState: BacktestSaveDrawingsRequest
): Promise<BacktestDrawingState> {
  const response = await apiClient.put<BacktestDrawingState>(
    `/backtest/runs/${encodeURIComponent(runId)}/drawings`,
    drawingState,
    { params: { interval_minutes: intervalMinutes } }
  );
  return response.data;
}

/** Load current committed orders, fills, positions, costs, and account state. */
export async function getBacktestSimulationState(
  runId: string
): Promise<BacktestSimulationState> {
  const response = await apiClient.get<BacktestSimulationState>(
    `/backtest/runs/${encodeURIComponent(runId)}/simulation`
  );
  return response.data;
}

/** Submit a protected market or limit order using the run's current revision. */
export async function submitBacktestSimulationOrder(
  runId: string,
  request: BacktestSimulationSubmitOrderRequest
): Promise<BacktestSimulationOperationResponse> {
  const response = await apiClient.post<BacktestSimulationOperationResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/simulation/orders`,
    request
  );
  return response.data;
}

/** Cancel one owned pending entry order. */
export async function cancelBacktestSimulationOrder(
  runId: string,
  orderId: string,
  request: BacktestSimulationCancelOrderRequest
): Promise<BacktestSimulationOperationResponse> {
  const response = await apiClient.post<BacktestSimulationOperationResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/simulation/orders/${encodeURIComponent(orderId)}/cancel`,
    request
  );
  return response.data;
}

/** Close one open position at the currently revealed candle close. */
export async function closeBacktestSimulationPosition(
  runId: string,
  positionId: string,
  request: BacktestSimulationClosePositionRequest
): Promise<BacktestSimulationOperationResponse> {
  const response = await apiClient.post<BacktestSimulationOperationResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/simulation/positions/${encodeURIComponent(positionId)}/close`,
    request
  );
  return response.data;
}

/** Change one or both protection levels on a single open position. */
export async function modifyBacktestSimulationProtection(
  runId: string,
  positionId: string,
  request: BacktestSimulationModifyProtectionRequest
): Promise<BacktestSimulationOperationResponse> {
  const response = await apiClient.put<BacktestSimulationOperationResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/simulation/positions/${encodeURIComponent(positionId)}/protection`,
    request
  );
  return response.data;
}

/** Load the versioned default sizing rows used to seed the Settings table. */
export async function getBacktestInstrumentSpecs(): Promise<BacktestInstrumentSpecs> {
  const response = await apiClient.get<BacktestInstrumentSpecs>(
    '/backtest/instrument-specs'
  );
  return response.data;
}

/** Update the saved risk budget percentage used for future entry orders. */
export async function updateBacktestSimulationRisk(
  runId: string,
  request: BacktestSimulationUpdateRiskRequest
): Promise<BacktestSimulationOperationResponse> {
  const response = await apiClient.put<BacktestSimulationOperationResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/simulation/risk`,
    request
  );
  return response.data;
}

/** Process every available source candle through the requested index. */
export async function advanceBacktestSimulation(
  runId: string,
  request: BacktestSimulationAdvanceRequest
): Promise<BacktestSimulationOperationResponse> {
  const response = await apiClient.post<BacktestSimulationOperationResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/simulation/advance`,
    request
  );
  return response.data;
}

/** Rewind before any entry is accepted in the current simulation generation. */
export async function rewindBacktestSimulation(
  runId: string,
  request: BacktestSimulationRewindRequest
): Promise<BacktestSimulationOperationResponse> {
  const response = await apiClient.post<BacktestSimulationOperationResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/simulation/rewind`,
    request
  );
  return response.data;
}

/** Confirm and reset a ready or complete run to its first replay candle. */
export async function resetBacktestSimulation(
  runId: string,
  request: BacktestSimulationResetRequest
): Promise<BacktestSimulationOperationResponse> {
  const response = await apiClient.post<BacktestSimulationOperationResponse>(
    `/backtest/runs/${encodeURIComponent(runId)}/simulation/reset`,
    request
  );
  return response.data;
}
