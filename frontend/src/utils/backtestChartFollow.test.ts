import { describe, expect, it } from 'vitest';
import {
  createBacktestChartFollowState,
  snapBacktestChartFollowToLive,
  updateBacktestChartFollowFromPosition,
  updateBacktestChartFollowOnCandle,
} from './backtestChartFollow';

describe('backtest chart follow state', () => {
  it('starts attached and follows new playback, step, or seek candles', () => {
    const initial = createBacktestChartFollowState(0, 60_000);
    const update = updateBacktestChartFollowOnCandle(initial, 120_000);

    expect(initial.isFollowing).toBe(true);
    expect(update.state.isFollowing).toBe(true);
    expect(update.shouldScroll).toBe(true);
    expect(update.state.latestCandleTime).toBe(120_000);
  });

  it('tracks panes independently when one is panned away', () => {
    const firstPane = createBacktestChartFollowState(0, 60_000);
    const secondPane = createBacktestChartFollowState(0, 60_000);
    const detached = updateBacktestChartFollowFromPosition(secondPane, -8);

    expect(detached.state.isFollowing).toBe(false);
    expect(firstPane.isFollowing).toBe(true);
    expect(updateBacktestChartFollowFromPosition(firstPane, 0).state.isFollowing)
      .toBe(true);
  });

  it('detaches on backward or forward pan and reattaches at the realtime edge', () => {
    const initial = createBacktestChartFollowState(0, 60_000);
    expect(updateBacktestChartFollowFromPosition(initial, -4).state.isFollowing)
      .toBe(false);
    expect(updateBacktestChartFollowFromPosition(initial, 4).state.isFollowing)
      .toBe(false);
    const detached = updateBacktestChartFollowFromPosition(initial, -4).state;
    expect(updateBacktestChartFollowFromPosition(detached, 0).state.isFollowing)
      .toBe(true);
  });

  it('preserves a detached range as playback advances', () => {
    const detached = updateBacktestChartFollowFromPosition(
      createBacktestChartFollowState(0, 60_000),
      -8
    ).state;
    const update = updateBacktestChartFollowOnCandle(detached, 120_000);

    expect(update.shouldScroll).toBe(false);
    expect(update.state.isFollowing).toBe(false);
    expect(update.state.latestCandleTime).toBe(120_000);
  });

  it('reactivates when replay catches a forward-panned view', () => {
    const forwardPanned = updateBacktestChartFollowFromPosition(
      createBacktestChartFollowState(0, 60_000),
      6
    ).state;
    const atLiveEdge = updateBacktestChartFollowFromPosition(forwardPanned, 0);
    const caughtUp = updateBacktestChartFollowOnCandle(atLiveEdge.state, 120_000);

    expect(caughtUp.state.isFollowing).toBe(true);
    expect(caughtUp.shouldScroll).toBe(true);
  });

  it('reattaches after a synchronized range lands on the realtime edge', () => {
    const detached = updateBacktestChartFollowFromPosition(
      createBacktestChartFollowState(0, 60_000),
      -5
    ).state;
    expect(updateBacktestChartFollowFromPosition(detached, 0).state.isFollowing)
      .toBe(true);
  });

  it('snaps an explicitly returned pane back to follow mode', () => {
    const detached = updateBacktestChartFollowFromPosition(
      createBacktestChartFollowState(0, 60_000),
      -5
    ).state;
    const snapped = snapBacktestChartFollowToLive(detached);

    expect(snapped.state.isFollowing).toBe(true);
    expect(snapped.followStateChanged).toBe(true);
  });

  it('does not scroll horizontally for an update to the current timeframe bar', () => {
    const initial = createBacktestChartFollowState(0, 60_000);
    const inPlaceUpdate = updateBacktestChartFollowOnCandle(initial, 60_000);

    expect(inPlaceUpdate.shouldScroll).toBe(false);
    expect(inPlaceUpdate.state.isFollowing).toBe(true);
  });
});
