import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  createSyncEngine,
  type ChartController,
  type SyncEngine,
  type SyncFlag,
  type SyncMember,
} from '@getcandlekit/charts';
import type { MouseEventParams, Time } from 'lightweight-charts';
import type { BacktestChartTab } from '../types/backtest.types';
import type { ReplayController } from '@getcandlekit/charts';
import { findNearestPriorCandleIndex } from '../utils/backtestChartSync';
import {
  createBacktestChartFollowState,
  snapBacktestChartFollowToLive,
  updateBacktestChartFollowFromPosition,
  updateBacktestChartFollowOnCandle,
} from '../utils/backtestChartFollow';
import { registerPanelSubscription } from '../utils/backtestPanelLifecycle';

function toUtcMilliseconds(time: Time | null | undefined): number | null {
  if (typeof time === 'number') return time * 1_000;
  if (time && typeof time === 'object' && 'year' in time) {
    return Date.UTC(time.year, time.month - 1, time.day);
  }
  return null;
}

/** Sync replay crosshairs while keeping chart viewport navigation pane-local. */
export function useBacktestChartSync(
  tabs: readonly BacktestChartTab[],
  symbol: string,
  replayController: ReplayController
) {
  const engine = useMemo<SyncEngine>(() => createSyncEngine(), []);
  const groupId = 'backtest-replay';
  const tabsRef = useRef(tabs);
  tabsRef.current = tabs;
  const detachRef = useRef(new Map<string, () => void>());
  const refreshLatestCandleRef = useRef(new Map<string, () => void>());
  const snapToLiveRef = useRef(new Map<string, () => void>());

  useEffect(() => {
    const detachments = detachRef.current;
    engine.createGroup({
      id: groupId,
      name: 'Backtest replay charts',
      flags: new Set<SyncFlag>(['cursor', 'crosshair']),
    });
    return () => {
      for (const detach of detachments.values()) detach();
      detachments.clear();
      engine.deleteGroup(groupId);
    };
  }, [engine, groupId]);

  useEffect(() => {
    let lastCursor: number | null = null;
    return replayController.subscribe((state) => {
      if (state.status !== 'ready' || state.cursor.ts === lastCursor) return;
      lastCursor = state.cursor.ts;
      engine.broadcast(groupId, {
        kind: 'cursor',
        ts: state.cursor.ts,
        sourcePanelId: null,
      });
      const cursorTime = state.cursor.ts;
      queueMicrotask(() => {
        const latestState = replayController.getState();
        if (latestState.status !== 'ready' || latestState.cursor.ts !== cursorTime) return;
        for (const refresh of refreshLatestCandleRef.current.values()) refresh();
      });
    });
  }, [engine, groupId, replayController]);

  const registerChart = useCallback((
    tabId: string,
    controller: ChartController,
    onFollowStateChange: (isFollowing: boolean) => void
  ) => {
    const chart = controller.getChart();
    const chartElement = chart.chartElement();
    const timeScale = chart.timeScale();
    const realtimeOffset = timeScale.options().rightOffset ?? 0;
    let isDisposed = false;
    let followFrame: number | null = null;
    let userRangeInputFrame: number | null = null;
    let isPointerDown = false;
    let userRangeInputPending = false;
    let cachedBars: ReturnType<ChartController['getBars']> | null = null;
    let cachedTimes: number[] = [];
    const getTab = () => tabsRef.current.find((tab) => tab.id === tabId);
    const getBars = () => controller.getBars();
    const getLatestBarTime = () => {
      const bars = getBars();
      return bars[bars.length - 1]?.ts ?? null;
    };
    let followState = createBacktestChartFollowState(
      realtimeOffset,
      getLatestBarTime()
    );

    const getTimes = () => {
      const bars = getBars();
      if (bars !== cachedBars) {
        cachedBars = bars;
        cachedTimes = bars.map((bar) => bar.ts);
      } else if (cachedTimes.length < bars.length) {
        for (let index = cachedTimes.length; index < bars.length; index += 1) {
          const bar = bars[index];
          if (bar) cachedTimes.push(bar.ts);
        }
      } else if (cachedTimes.length > bars.length) {
        cachedTimes.length = bars.length;
      }
      return cachedTimes;
    };

    const updateFollowStateFromPosition = () => {
      const update = updateBacktestChartFollowFromPosition(
        followState,
        timeScale.scrollPosition()
      );
      followState = update.state;
      if (update.followStateChanged) onFollowStateChange(followState.isFollowing);
    };

    const followLatestCandle = () => {
      if (isDisposed || !followState.isFollowing || followFrame !== null) return;
      followFrame = window.requestAnimationFrame(() => {
        followFrame = null;
        if (isDisposed || !followState.isFollowing) return;
        timeScale.scrollToPosition(realtimeOffset, false);
      });
    };

    const snapToLive = () => {
      if (isDisposed) return;
      timeScale.scrollToPosition(realtimeOffset, false);
      const update = snapBacktestChartFollowToLive(followState);
      followState = update.state;
      if (update.followStateChanged) onFollowStateChange(true);
    };

    const refreshLatestCandle = () => {
      if (isDisposed) return;
      const update = updateBacktestChartFollowOnCandle(
        followState,
        getLatestBarTime()
      );
      followState = update.state;
      if (!update.shouldScroll) return;

      // Range movement caused by replay should not overwrite a detached sibling pane.
      followLatestCandle();
    };

    const scheduleUserViewportCheck = (framesToSettle = 2) => {
      userRangeInputPending = true;
      if (userRangeInputFrame !== null) {
        window.cancelAnimationFrame(userRangeInputFrame);
      }
      let framesRemaining = framesToSettle;
      const check = () => {
        if (isDisposed) return;
        const range = timeScale.getVisibleLogicalRange();
        if (range) updateFollowStateFromPosition();
        framesRemaining -= 1;
        if (framesRemaining > 0) {
          userRangeInputFrame = window.requestAnimationFrame(check);
          return;
        }
        userRangeInputFrame = null;
        userRangeInputPending = false;
      };
      userRangeInputFrame = window.requestAnimationFrame(check);
    };

    const onPointerDown = (event: PointerEvent) => {
      if (event.button === 2) return;
      isPointerDown = true;
    };
    const onPointerUp = () => {
      if (!isPointerDown) return;
      isPointerDown = false;
      scheduleUserViewportCheck();
    };
    const onWheel = () => scheduleUserViewportCheck();
    const onDoubleClick = (event: MouseEvent) => {
      const bounds = chartElement.getBoundingClientRect();
      if (event.clientY >= bounds.bottom - 32) {
        event.preventDefault();
        event.stopPropagation();
        snapToLive();
        return;
      }
      scheduleUserViewportCheck(30);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.startsWith('Arrow') || ['+', '-', '=', '_', 'PageUp', 'PageDown'].includes(event.key)) {
        scheduleUserViewportCheck();
      }
    };

    // A new or remounted pane starts at the latest revealed candle.
    timeScale.scrollToPosition(realtimeOffset, false);
    onFollowStateChange(followState.isFollowing);

    function setCrosshairAtTime(ts: number | null, y?: number | null) {
      if (ts === null) {
        chart.clearCrosshairPosition();
        return;
      }
      const bars = getBars();
      const times = getTimes();
      const index = findNearestPriorCandleIndex(times, ts) ?? -1;
      const targetBar = index >= 0 ? bars[index] : undefined;
      if (!targetBar) {
        chart.clearCrosshairPosition();
        return;
      }
      const price = typeof y === 'number' && Number.isFinite(y) ? y : targetBar.close;
      chart.setCrosshairPosition(
        price,
        Math.floor(targetBar.ts / 1_000) as Time,
        controller.getSeries()
      );
    }

    const member: SyncMember = {
      panelId: tabId,
      viewport: {
        getVisibleLogicalRange: () => timeScale.getVisibleLogicalRange(),
        setVisibleLogicalRange: (range) => timeScale.setVisibleLogicalRange(range),
        setCrosshairAtTime,
      },
      getSession: () => {
        const tab = getTab();
        return {
          symbol,
          interval: `${tab?.interval_minutes ?? 1}m`,
        };
      },
      apply: (event) => {
        if (event.kind === 'crosshair') {
          setCrosshairAtTime(event.ts, event.y);
          return;
        }
        // Cursor synchronization is owned by the single shared controller and
        // its per-tab bounded data updates. Chart time ranges stay local.
      },
    };

    const detachMember = engine.attach(groupId, member);

    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      const ts = toUtcMilliseconds(param.time ?? null);
      let y: number | null = null;
      const seriesValue = param.seriesData.get(controller.getSeries()) as
        | { close?: number; value?: number }
        | undefined;
      if (typeof seriesValue?.close === 'number') y = seriesValue.close;
      else if (typeof seriesValue?.value === 'number') y = seriesValue.value;
      engine.broadcast(groupId, {
        kind: 'crosshair',
        ts,
        y,
        sourcePanelId: tabId,
      });
    };

    const onVisibleRangeChange = (range: { from: number; to: number } | null) => {
      if (range && (isPointerDown || userRangeInputPending)) {
        updateFollowStateFromPosition();
      }
    };

    chart.subscribeCrosshairMove(onCrosshairMove);
    timeScale.subscribeVisibleLogicalRangeChange(onVisibleRangeChange);
    chartElement.addEventListener('pointerdown', onPointerDown, true);
    window.addEventListener('pointerup', onPointerUp, true);
    window.addEventListener('pointercancel', onPointerUp, true);
    chartElement.addEventListener('wheel', onWheel, { capture: true, passive: true });
    chartElement.addEventListener('dblclick', onDoubleClick, true);
    chartElement.addEventListener('keydown', onKeyDown, true);
    refreshLatestCandleRef.current.set(tabId, refreshLatestCandle);
    snapToLiveRef.current.set(tabId, snapToLive);

    return registerPanelSubscription(detachRef.current, tabId, () => {
      isDisposed = true;
      if (followFrame !== null) window.cancelAnimationFrame(followFrame);
      if (userRangeInputFrame !== null) window.cancelAnimationFrame(userRangeInputFrame);
      if (snapToLiveRef.current.get(tabId) === snapToLive) {
        snapToLiveRef.current.delete(tabId);
      }
      if (refreshLatestCandleRef.current.get(tabId) === refreshLatestCandle) {
        refreshLatestCandleRef.current.delete(tabId);
      }
      chart.unsubscribeCrosshairMove(onCrosshairMove);
      timeScale.unsubscribeVisibleLogicalRangeChange(onVisibleRangeChange);
      chartElement.removeEventListener('pointerdown', onPointerDown, true);
      window.removeEventListener('pointerup', onPointerUp, true);
      window.removeEventListener('pointercancel', onPointerUp, true);
      chartElement.removeEventListener('wheel', onWheel, true);
      chartElement.removeEventListener('dblclick', onDoubleClick, true);
      chartElement.removeEventListener('keydown', onKeyDown, true);
      detachMember();
    });
  }, [engine, groupId, symbol]);

  const unregisterChart = useCallback((tabId: string) => {
    detachRef.current.get(tabId)?.();
  }, []);

  const snapToLive = useCallback((tabId: string) => {
    snapToLiveRef.current.get(tabId)?.();
  }, []);

  return {
    registerChart,
    unregisterChart,
    snapToLive,
  };
}
