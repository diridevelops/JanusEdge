const DEFAULT_REALTIME_EDGE_TOLERANCE = 0.5;

export interface BacktestChartFollowState {
  isFollowing: boolean;
  realtimeOffset: number;
  latestCandleTime: number | null;
}

export interface BacktestChartFollowUpdate {
  state: BacktestChartFollowState;
  followStateChanged: boolean;
}

export interface BacktestChartCandleUpdate extends BacktestChartFollowUpdate {
  shouldScroll: boolean;
}

export function createBacktestChartFollowState(
  realtimeOffset: number,
  latestCandleTime: number | null
): BacktestChartFollowState {
  return {
    isFollowing: true,
    realtimeOffset,
    latestCandleTime,
  };
}

/** True when the chart's right edge is aligned with its normal realtime offset. */
export function isAtRealtimeEdge(
  scrollPosition: number,
  realtimeOffset: number,
  tolerance = DEFAULT_REALTIME_EDGE_TOLERANCE
): boolean {
  return Number.isFinite(scrollPosition)
    && Number.isFinite(realtimeOffset)
    && Math.abs(scrollPosition - realtimeOffset) <= tolerance;
}

export function updateBacktestChartFollowFromPosition(
  state: BacktestChartFollowState,
  scrollPosition: number
): BacktestChartFollowUpdate {
  const isFollowing = isAtRealtimeEdge(scrollPosition, state.realtimeOffset);
  return {
    state: isFollowing === state.isFollowing ? state : { ...state, isFollowing },
    followStateChanged: isFollowing !== state.isFollowing,
  };
}

/** Reattach at the live edge if replay has caught up to a forward-panned pane. */
export function updateBacktestChartFollowOnCandle(
  state: BacktestChartFollowState,
  latestCandleTime: number | null
): BacktestChartCandleUpdate {
  const candleChanged = latestCandleTime !== null
    && latestCandleTime !== state.latestCandleTime;
  const nextState = {
    ...state,
    latestCandleTime,
  };
  return {
    state: nextState,
    followStateChanged: false,
    shouldScroll: candleChanged && state.isFollowing,
  };
}

export function snapBacktestChartFollowToLive(
  state: BacktestChartFollowState
): BacktestChartFollowUpdate {
  return {
    state: state.isFollowing ? state : { ...state, isFollowing: true },
    followStateChanged: !state.isFollowing,
  };
}
