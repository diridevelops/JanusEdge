import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createSyncEngine,
  type ChartController,
  type SyncEngine,
  type SyncEvent,
  type SyncFlag,
  type SyncMember,
} from '@getcandlekit/charts';
import type { MouseEventParams, Time } from 'lightweight-charts';
import type { BacktestChartTab } from '../types/backtest.types';
import type { ReplayController } from '@getcandlekit/charts';
import {
  findNearestPriorCandleIndex,
  logicalRangeToUtcRange,
  roundUtcRangeOutward,
  utcRangeToLogicalRange,
} from '../utils/backtestChartSync';
import {
  createBacktestChartFollowState,
  snapBacktestChartFollowToLive,
  updateBacktestChartFollowFromPosition,
  updateBacktestChartFollowOnCandle,
} from '../utils/backtestChartFollow';
import { registerPanelSubscription } from '../utils/backtestPanelLifecycle';
import type { BacktestSyncOptions } from '../components/backtest/BacktestSyncControls';

function toUtcMilliseconds(time: Time | null | undefined): number | null {
  if (typeof time === 'number') return time * 1_000;
  if (time && typeof time === 'object' && 'year' in time) {
    return Date.UTC(time.year, time.month - 1, time.day);
  }
  return null;
}

function approximatelyEqual(
  left: { from: number; to: number },
  right: { from: number; to: number }
): boolean {
  return Math.abs(left.from - right.from) < 0.05
    && Math.abs(left.to - right.to) < 0.05;
}

function classifyRangeChange(
  previous: { from: number; to: number },
  next: { from: number; to: number }
): 'pan' | 'zoom' {
  const previousSpan = previous.to - previous.from;
  const nextSpan = next.to - next.from;
  return Math.abs(previousSpan - nextSpan) > Math.max(0.5, previousSpan * 0.01)
    ? 'zoom'
    : 'pan';
}

function getEventUtcRange(
  event: SyncEvent
): { from: number; to: number } | null {
  return event.kind === 'timeRange'
    ? { from: event.from, to: event.to }
    : null;
}

/** Route UTC crosshair and visible-range events through CandleKit's SyncEngine. */
export function useBacktestChartSync(
  tabs: readonly BacktestChartTab[],
  symbol: string,
  replayController: ReplayController
) {
  const engine = useMemo<SyncEngine>(() => createSyncEngine(), []);
  const groupId = 'backtest-replay';
  const [options, setOptions] = useState<BacktestSyncOptions>({
    crosshair: true,
    pan: true,
    zoom: true,
  });
  const optionsRef = useRef(options);
  optionsRef.current = options;
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
      flags: new Set<SyncFlag>(['cursor', 'crosshair', 'timeRange']),
    });
    return () => {
      for (const detach of detachments.values()) detach();
      detachments.clear();
      engine.deleteGroup(groupId);
    };
  }, [engine, groupId]);

  useEffect(() => {
    const flags = new Set<SyncFlag>(['cursor']);
    if (options.crosshair) flags.add('crosshair');
    if (options.pan || options.zoom) flags.add('timeRange');
    engine.setFlags(groupId, flags);
  }, [engine, groupId, options]);

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
    const lastRangeRef: { current: { from: number; to: number } | null } = { current: null };
    const appliedRangeRef: { current: { from: number; to: number } | null } = { current: null };
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
        lastRangeRef.current = timeScale.getVisibleLogicalRange();
      });
    };

    const snapToLive = () => {
      if (isDisposed) return;
      timeScale.scrollToPosition(realtimeOffset, false);
      const update = snapBacktestChartFollowToLive(followState);
      followState = update.state;
      if (update.followStateChanged) onFollowStateChange(true);
      lastRangeRef.current = timeScale.getVisibleLogicalRange();
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

    const applyUserViewportChange = (range: { from: number; to: number }) => {
      const previous = lastRangeRef.current;
      lastRangeRef.current = range;
      updateFollowStateFromPosition();
      if (!previous || approximatelyEqual(previous, range)) return;

      const changeKind = classifyRangeChange(previous, range);
      const currentOptions = optionsRef.current;
      if ((changeKind === 'pan' && !currentOptions.pan)
        || (changeKind === 'zoom' && !currentOptions.zoom)) return;

      const tab = getTab();
      const utcRange = logicalRangeToUtcRange(getTimes(), range);
      if (!tab || !utcRange) return;
      engine.broadcast(groupId, {
        kind: 'timeRange',
        from: utcRange.from,
        to: utcRange.to,
        sourcePanelId: tabId,
      });
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
        if (range) applyUserViewportChange(range);
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
    lastRangeRef.current = timeScale.getVisibleLogicalRange();
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
        if (event.kind === 'timeRange') {
          const utcRange = getEventUtcRange(event);
          const tab = getTab();
          if (!utcRange || !tab) return;
          const times = getTimes();
          const rounded = roundUtcRangeOutward(utcRange, tab.interval_minutes);
          const logical = utcRangeToLogicalRange(times, rounded);
          if (!logical) return;
          appliedRangeRef.current = logical;
          lastRangeRef.current = logical;
          timeScale.setVisibleLogicalRange(logical);
          updateFollowStateFromPosition();
          return;
        }
        // Cursor synchronization is owned by the single shared controller and
        // its per-tab bounded data updates; no chart can disable or clone it.
      },
    };

    const detachMember = engine.attach(groupId, member);

    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      if (!optionsRef.current.crosshair) return;
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
      if (!range) {
        lastRangeRef.current = null;
        return;
      }
      if (appliedRangeRef.current && approximatelyEqual(appliedRangeRef.current, range)) {
        appliedRangeRef.current = null;
        lastRangeRef.current = range;
        updateFollowStateFromPosition();
        return;
      }
      if (isPointerDown || userRangeInputPending) {
        applyUserViewportChange(range);
        return;
      }

      // Replay data updates, follow snaps, and layout changes can emit range
      // notifications. Only a user's chart gesture can detach or sync a pane.
      lastRangeRef.current = range;
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
    options,
    setOptions,
    registerChart,
    unregisterChart,
    snapToLive,
  };
}
