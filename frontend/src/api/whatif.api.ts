import type {
  SimulationResponse,
  StopAnalysisResponse,
  WickedOutTradesResponse,
} from '../types/whatif.types';
import apiClient from './client';

/** Fetch R-normalized overshoot stop analysis. */
export async function getStopAnalysis(
  params: Record<string, string>,
): Promise<StopAnalysisResponse> {
  const res = await apiClient.get<StopAnalysisResponse>(
    '/whatif/stop-analysis',
    { params },
  );
  return res.data;
}

/** Fetch wicked-out trades with tick-data availability. */
export async function getWickedOutTrades(
  params: Record<string, string>,
): Promise<WickedOutTradesResponse> {
  const res = await apiClient.get<WickedOutTradesResponse>(
    '/whatif/wicked-out-trades',
    { params },
  );
  return res.data;
}

/** Run what-if stop widening simulation. */
export async function runSimulation(
  rWidening: number,
  replayMode: 'ohlc' | 'tick',
  params: Record<string, string>,
): Promise<SimulationResponse> {
  const res = await apiClient.post<SimulationResponse>(
    '/whatif/simulate',
    { r_widening: rWidening, replay_mode: replayMode },
    { params },
  );
  return res.data;
}
