import apiClient from './client';
import type {
  BacktestCandle,
  BacktestChartTab,
  BacktestDrawingState,
  BacktestInstrumentCatalog,
  BacktestPreparationNotice,
  BacktestReplayPosition,
  BacktestReplayPositionRequest,
  BacktestRunDetail,
  BacktestRunSummary,
  BacktestSaveDrawingsRequest,
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

/** Fetch the user's preparing and ready runs. */
export async function listBacktestRuns(): Promise<BacktestRunSummary[]> {
  const response = await apiClient.get<{ runs: BacktestRunSummary[] }>(
    '/backtest/runs'
  );
  return response.data.runs;
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

/** Persist the run's full, nonempty ordered chart-tab list. */
export async function saveBacktestChartTabs(
  runId: string,
  tabs: BacktestChartTab[]
): Promise<BacktestChartTab[]> {
  const response = await apiClient.put<{ tabs: BacktestChartTab[] }>(
    `/backtest/runs/${encodeURIComponent(runId)}/chart-tabs`,
    { tabs }
  );
  return response.data.tabs;
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
