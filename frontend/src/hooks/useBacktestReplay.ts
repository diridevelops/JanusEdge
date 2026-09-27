import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createReplayController,
  type Bar,
  type ChartController,
  type ReplayController,
  type ReplayState,
} from '@getcandlekit/charts';
import {
  getBacktestCandlesForDate,
  listBacktestCandleDates,
  saveBacktestReplayPosition,
} from '../api/backtests.api';
import type {
  BacktestCandle,
  BacktestChartTab,
  BacktestRunDetail,
} from '../types/backtest.types';
import {
  aggregateRevealedCandles,
  appendRevealedCandle,
  type BacktestAggregatedBar,
} from '../utils/backtestCandles';
import {
  createBacktestReplayDataSource,
  createCandleKitControlsAdapter,
  createReplayPositionWriter,
} from '../utils/backtestReplay';
import { getBacktestPriceFormat } from '../utils/backtestPriceFormat';

export type BacktestReplayStatus = 'loading' | 'ready' | 'error';

interface TabBarsSnapshot {
  intervalMinutes: number;
  bars: BacktestAggregatedBar[];
}

function toCandle(bar: Bar): BacktestCandle {
  return {
    time_ms: bar.ts,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    ...(typeof bar.volume === 'number' ? { volume: bar.volume } : {}),
  };
}

function toBar(bar: BacktestAggregatedBar): Bar {
  return {
    ts: bar.ts,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    ...(typeof bar.volume === 'number' ? { volume: bar.volume } : {}),
  };
}

function isReadyState(state: ReplayState): state is Extract<ReplayState, { status: 'ready' }> {
  return state.status === 'ready';
}

function waitForCursor(
  controller: ReplayController,
  timeMs: number,
  isCancelled: () => boolean
): Promise<void> {
  const current = controller.getState();
  if (isReadyState(current) && current.cursor.ts === timeMs && !current.playing) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    let timeoutId = 0;
    const unsubscribe = controller.subscribe((state) => {
      if (isCancelled()) {
        window.clearTimeout(timeoutId);
        unsubscribe();
        resolve();
      } else if (isReadyState(state) && state.cursor.ts === timeMs && !state.playing) {
        window.clearTimeout(timeoutId);
        unsubscribe();
        resolve();
      } else if (state.status === 'error') {
        window.clearTimeout(timeoutId);
        unsubscribe();
        reject(new Error(state.error));
      }
    });
    timeoutId = window.setTimeout(() => {
      unsubscribe();
      reject(new Error('Timed out while restoring the saved replay cursor.'));
    }, 15_000);
  });
}

/**
 * One CandleKit controller owns the one-minute sequence for this run. Every
 * tab derives its bars from the controller's cursor-bounded source prefix.
 */
export function useBacktestReplay(
  run: BacktestRunDetail,
  tabs: readonly BacktestChartTab[]
) {
  // The controller is run-scoped, so a route parameter change must replace it.
  const controller = useMemo(
    () => createReplayController({
      cacheDays: 400,
      prefetchBackwardDays: 400,
      prefetchForwardOnTailPct: 0.9,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rerun-scoped controller
    [run.id]
  );
  const [status, setStatus] = useState<BacktestReplayStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [cursorSaveError, setCursorSaveError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [controlsController, setControlsController] = useState<ReplayController | null>(null);
  const [cursorTimeMs, setCursorTimeMs] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const runRef = useRef(run);
  runRef.current = run;
  const tabsRef = useRef(tabs);
  tabsRef.current = tabs;
  const snapshotsRef = useRef(new Map<string, TabBarsSnapshot>());
  const chartControllersRef = useRef(new Map<string, ChartController>());
  const writerRef = useRef<ReturnType<typeof createReplayPositionWriter> | null>(null);
  const loadPromiseRef = useRef<{ key: string; promise: Promise<void> } | null>(null);
  const effectLifecycleRef = useRef({ generation: 0 });
  const allCandleTimesRef = useRef<number[]>([]);
  const lastProcessedCursorRef = useRef<number | null>(null);
  const restoreInProgressRef = useRef(true);
  const lastObservedReplayRef = useRef<{ cursorTimeMs: number; playing: boolean } | null>(null);
  const drawingFlushersRef = useRef(new Map<string, () => Promise<void> | void>());

  const getTabBars = useCallback((tabId: string): readonly BacktestAggregatedBar[] => (
    snapshotsRef.current.get(tabId)?.bars ?? []
  ), []);

  const registerTabChart = useCallback((
    tabId: string,
    chart: ChartController | null
  ): (() => void) | void => {
    if (!chart) {
      chartControllersRef.current.delete(tabId);
      return;
    }
    chart.getSeries().applyOptions({
      priceFormat: getBacktestPriceFormat(runRef.current.instrument),
    });
    chartControllersRef.current.set(tabId, chart);
    const snapshot = snapshotsRef.current.get(tabId);
    chart.setData(snapshot?.bars.map(toBar) ?? []);
    return () => {
      if (chartControllersRef.current.get(tabId) === chart) {
        chartControllersRef.current.delete(tabId);
      }
    };
  }, []);

  const registerDrawingFlusher = useCallback((tabId: string, flush: () => Promise<void> | void) => {
    drawingFlushersRef.current.set(tabId, flush);
    return () => {
      if (drawingFlushersRef.current.get(tabId) === flush) {
        drawingFlushersRef.current.delete(tabId);
      }
    };
  }, []);

  const rebuildAtCursor = useCallback((cursorTimeMs: number) => {
    const runDetail = runRef.current;
    const sourceBars = controller.getBarsUpToCursor(runDetail.instrument, '1m')
      .map(toCandle);
    const cursorIndex = sourceBars.length - 1;

    for (const tab of tabsRef.current) {
      const bars = aggregateRevealedCandles(
        sourceBars,
        tab.interval_minutes,
        cursorIndex
      );
      snapshotsRef.current.set(tab.id, {
        intervalMinutes: tab.interval_minutes,
        bars,
      });
      chartControllersRef.current.get(tab.id)?.setData(bars.map(toBar));
    }
    lastProcessedCursorRef.current = cursorTimeMs;
    return sourceBars;
  }, [controller]);

  const appendAtCursor = useCallback((bar: Bar, cursorTimeMs: number) => {
    const candle = toCandle(bar);
    for (const tab of tabsRef.current) {
      const snapshot = snapshotsRef.current.get(tab.id);
      const visibleBars = controller.getBarsUpToCursor(runRef.current.instrument, '1m');
      const bars = snapshot?.intervalMinutes === tab.interval_minutes
        ? appendRevealedCandle(snapshot.bars, candle, tab.interval_minutes)
        : aggregateRevealedCandles(
          visibleBars.map(toCandle),
          tab.interval_minutes,
          visibleBars.length - 1
        );
      snapshotsRef.current.set(tab.id, {
        intervalMinutes: tab.interval_minutes,
        bars,
      });
      const updated = bars[bars.length - 1];
      if (updated) chartControllersRef.current.get(tab.id)?.updateBar(toBar(updated));
    }
    lastProcessedCursorRef.current = cursorTimeMs;
  }, [controller]);

  const enqueueCursorSave = useCallback((timeMs: number) => {
    const runDetail = runRef.current;
    const visibleBars = controller.getBarsUpToCursor(runDetail.instrument, '1m');
    const sourceCandleIndex = visibleBars.length - 1;
    if (sourceCandleIndex < 0 || visibleBars[sourceCandleIndex]?.ts !== timeMs) {
      setCursorSaveError('The replay cursor is not on an available source candle.');
      return;
    }
    writerRef.current?.enqueue({ source_candle_index: sourceCandleIndex, time_ms: timeMs });
  }, [controller]);

  const retryLoad = useCallback(() => {
    setError(null);
    setStatus('loading');
    setLoadAttempt((attempt) => attempt + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const effectLifecycle = effectLifecycleRef.current;
    const effectGeneration = ++effectLifecycle.generation;
    const drawingFlushers = drawingFlushersRef.current;
    restoreInProgressRef.current = true;
    lastProcessedCursorRef.current = null;
    setStatus('loading');
    setError(null);
    setCursorSaveError(null);
    setControlsController(null);
    setCursorTimeMs(null);
    setIsPlaying(false);
    snapshotsRef.current.clear();
    allCandleTimesRef.current = [];
    lastObservedReplayRef.current = null;

    const chartControllers = chartControllersRef.current;
    const runDetail = runRef.current;
    const snapshot = runDetail.snapshot;
    const savedCursor = runDetail.replay_cursor;
    if (!snapshot || !savedCursor || snapshot.candle_count < 1) {
      setStatus('error');
      setError('This ready run is missing its immutable candle snapshot or saved replay cursor.');
      return () => {
        cancelled = true;
      };
    }
    const readySnapshot = snapshot;
    const readyCursor = savedCursor;

    const writer = createReplayPositionWriter(
      runDetail.id,
      savedCursor.revision,
      saveBacktestReplayPosition,
      () => setCursorSaveError('Could not save the replay position. Reload the run to recover the latest revision.'),
      () => setCursorSaveError(null)
    );
    writerRef.current = writer;

    const source = createBacktestReplayDataSource(
      runDetail.id,
      {
        firstTimeMs: readySnapshot.first_time_ms,
        lastTimeMs: readySnapshot.last_time_ms,
      },
      {
        listCandleDates: listBacktestCandleDates,
        getCandlesForDate: getBacktestCandlesForDate,
      }
    );

    const unsubscribeState = controller.subscribe((nextState) => {
      if (cancelled || restoreInProgressRef.current || !isReadyState(nextState)) {
        if (nextState.status === 'error' && !cancelled) {
          setStatus('error');
          setError(nextState.error);
        }
        return;
      }

      setCursorTimeMs(nextState.cursor.ts);
      setIsPlaying(nextState.playing);
      const previousReplayState = lastObservedReplayRef.current;
      if (previousReplayState && (
        (previousReplayState.playing && !nextState.playing)
        || (!nextState.playing && previousReplayState.cursorTimeMs !== nextState.cursor.ts)
      )) {
        for (const flush of drawingFlushersRef.current.values()) {
          void Promise.resolve().then(flush).catch(() => undefined);
        }
      }
      lastObservedReplayRef.current = {
        cursorTimeMs: nextState.cursor.ts,
        playing: nextState.playing,
      };

      const previousCursor = lastProcessedCursorRef.current;
      if (!nextState.playing) void writerRef.current?.flush();
      if (previousCursor === nextState.cursor.ts) return;

      queueMicrotask(() => {
        if (cancelled || restoreInProgressRef.current) return;
        const latestState = controller.getState();
        if (!isReadyState(latestState)
          || lastProcessedCursorRef.current === latestState.cursor.ts) return;
        const sourceBars = rebuildAtCursor(latestState.cursor.ts);
        if (sourceBars.length > 0) enqueueCursorSave(latestState.cursor.ts);
        if (!latestState.playing) void writer.flush();
      });
    });

    const unsubscribeBar = controller.onBar((event) => {
      if (
        cancelled
        || restoreInProgressRef.current
        || event.symbol !== runDetail.instrument
        || event.interval !== '1m'
      ) return;

      const state = controller.getState();
      if (!isReadyState(state) || state.cursor.ts !== event.ts) return;

      const previousCursor = lastProcessedCursorRef.current;
      if (previousCursor !== null && event.ts > previousCursor) {
        appendAtCursor(event.bar, event.ts);
      } else {
        rebuildAtCursor(event.ts);
      }
      enqueueCursorSave(event.ts);
      if (!state.playing) void writer.flush();
    });

    async function loadReplay() {
      try {
        const loadKey = `${runDetail.id}:${loadAttempt}`;
        let load = loadPromiseRef.current;
        if (load?.key !== loadKey) {
          const promise = controller.load({
            id: runDetail.id,
            series: [{ symbol: runDetail.instrument, interval: '1m' }],
            // Loading from the last saved snapshot candle causes CandleKit to load
            // all prior available dates. With a one-year maximum, 400 dates covers
            // the full run and gives ReplayControls its complete seek window.
            start: readySnapshot.last_time_ms,
            end: readySnapshot.last_time_ms,
            source,
          });
          load = { key: loadKey, promise };
          loadPromiseRef.current = load;
        }
        await load.promise;
        if (cancelled) return;

        const loadedState = controller.getState();
        if (!isReadyState(loadedState)) {
          throw new Error(
            loadedState.status === 'error'
              ? loadedState.error
              : 'CandleKit did not finish loading the run snapshot.'
          );
        }

        controller.pause();
        const completeSource = controller.getBarsUpToCursor(runDetail.instrument, '1m');
        const savedBar = completeSource[readyCursor.source_candle_index];
        if (
          completeSource.length !== readySnapshot.candle_count
          || completeSource[0]?.ts !== readySnapshot.first_time_ms
          || completeSource[completeSource.length - 1]?.ts !== readySnapshot.last_time_ms
        ) {
          throw new Error('The replay source did not load the complete immutable snapshot.');
        }
        if (!savedBar || savedBar.ts !== readyCursor.time_ms) {
          throw new Error('The saved replay cursor does not match its source candle index.');
        }

        allCandleTimesRef.current = completeSource.map((bar) => bar.ts);
        const replayStartSourceIndex = Math.max(
          0,
          Math.min(
            readySnapshot.replay_start_source_index ?? 0,
            allCandleTimesRef.current.length - 1
          )
        );
        const adapter = createCandleKitControlsAdapter(
          controller,
          allCandleTimesRef.current.slice(replayStartSourceIndex)
        );

        if (loadedState.cursor.ts !== readyCursor.time_ms) {
          controller.seek(readyCursor.time_ms);
          await waitForCursor(
            controller,
            readyCursor.time_ms,
            () => cancelled
          );
        }
        if (cancelled) return;

        controller.pause();
        rebuildAtCursor(readyCursor.time_ms);
        restoreInProgressRef.current = false;
        lastObservedReplayRef.current = {
          cursorTimeMs: readyCursor.time_ms,
          playing: false,
        };
        setCursorTimeMs(readyCursor.time_ms);
        setIsPlaying(false);
        setControlsController(adapter);
        setStatus('ready');
      } catch (loadError: unknown) {
        if (cancelled) return;
        restoreInProgressRef.current = true;
        setStatus('error');
        setError(loadError instanceof Error ? loadError.message : 'Could not load this replay.');
      }
    }

    void loadReplay();

    return () => {
      cancelled = true;
      restoreInProgressRef.current = true;
      unsubscribeState();
      unsubscribeBar();
      controller.pause();
      void writer.flush();
      for (const flush of drawingFlushers.values()) {
        void Promise.resolve().then(flush).catch(() => undefined);
      }
      drawingFlushers.clear();
      writerRef.current = null;
      for (const chart of chartControllers.values()) chart.setData([]);
      chartControllers.clear();
      // React Strict Mode replays effects immediately in development. Defer
      // unloading so the replayed setup can reuse the in-flight snapshot load.
      queueMicrotask(() => {
        if (effectLifecycle.generation === effectGeneration) controller.unload();
      });
    };
  }, [
    appendAtCursor,
    controller,
    enqueueCursorSave,
    loadAttempt,
    rebuildAtCursor,
    run.id,
  ]);

  useEffect(() => {
    if (status !== 'ready') return;
    const state = controller.getState();
    if (!isReadyState(state)) return;
    const sourceBars = controller.getBarsUpToCursor(run.instrument, '1m').map(toCandle);
    const cursorIndex = sourceBars.length - 1;

    for (const tab of tabs) {
      const current = snapshotsRef.current.get(tab.id);
      if (current?.intervalMinutes === tab.interval_minutes) continue;
      const bars = aggregateRevealedCandles(sourceBars, tab.interval_minutes, cursorIndex);
      snapshotsRef.current.set(tab.id, { intervalMinutes: tab.interval_minutes, bars });
      chartControllersRef.current.get(tab.id)?.setData(bars.map(toBar));
    }

    for (const [tabId, snapshot] of snapshotsRef.current) {
      if (!tabs.some((tab) => tab.id === tabId)) {
        snapshotsRef.current.delete(tabId);
        chartControllersRef.current.delete(tabId);
      } else if (snapshot.bars.length === 0 && sourceBars.length > 0) {
        const tab = tabs.find((candidate) => candidate.id === tabId);
        if (tab) {
          const bars = aggregateRevealedCandles(sourceBars, tab.interval_minutes, cursorIndex);
          snapshotsRef.current.set(tabId, { intervalMinutes: tab.interval_minutes, bars });
          chartControllersRef.current.get(tabId)?.setData(bars.map(toBar));
        }
      }
    }
  }, [controller, run.instrument, status, tabs]);

  return {
    controller,
    controlsController,
    status,
    error,
    cursorSaveError,
    cursorTimeMs,
    isPlaying,
    retryLoad,
    getTabBars,
    registerTabChart,
    registerDrawingFlusher,
    allCandleTimes: allCandleTimesRef.current,
  };
}
