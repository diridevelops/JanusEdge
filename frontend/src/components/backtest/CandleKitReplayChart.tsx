import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { ChevronsRight } from 'lucide-react';
import {
  darkTheme,
  DrawingController,
  DrawingEngine,
  lightTheme,
  type ChartTheme,
} from '@getcandlekit/charts';
import { ChartView, DrawingToolbar, type ChartViewApi } from '@getcandlekit/charts/react';
import {
  getBacktestDrawingState,
  saveBacktestDrawingState,
} from '../../api/backtests.api';
import { useChartColors } from '../../hooks/useChartColors';
import type { BacktestDrawingState } from '../../types/backtest.types';
import {
  createDrawingStateWriter,
  filterDrawingsAtReplayCursor,
  getDrawingIds,
  normalizeSerializedDrawingState,
  transformDrawingPrices,
  reconcileVisibleDrawingChanges,
} from '../../utils/backtestDrawings';
import {
  discardPendingPanelFlush,
  registerPendingPanelFlush,
  retryPendingPanelFlush,
  waitForPendingPanelFlush,
} from '../../utils/backtestPanelLifecycle';
import { createBacktestTimeFormatters } from '../../utils/backtestTimeFormat';
import { normalizeBacktestPrice } from '../../utils/backtestPriceFormat';
import { BacktestBracketPreview } from './BacktestBracketPreview';
import { BacktestPositionOverlay } from './BacktestPositionOverlay';
import { useBacktestSimulationChartUi } from './BacktestSimulationContext';
import { useChartApi } from '@getcandlekit/charts/react';

const EMPTY_DATA: never[] = [];
const CANDLEKIT_VERSION = '0.1.0';
const DRAWING_SCHEMA_VERSION = 1;

type HydrationState = {
  key: string;
  status: 'loading' | 'ready' | 'error';
  error: string | null;
};

type SaveState = {
  key: string;
  status: 'saved' | 'saving' | 'error' | 'conflict';
  error: string | null;
};

type DrawingSession = {
  key: string;
  engine: DrawingEngine;
  controller: DrawingController;
};

interface CandleKitReplayChartProps {
  tabId: string;
  runId: string;
  intervalMinutes: number;
  displayTimezone: string;
  blindMode: boolean;
  normalizedReferencePrice: number | null;
  cursorTimeMs: number;
  registerDrawingFlusher: (
    tabId: string,
    flush: () => Promise<void> | void
  ) => () => void;
  onChartReady: (
    tabId: string,
    api: ChartViewApi,
    onFollowStateChange: (isFollowing: boolean) => void
  ) => void | (() => void);
  snapToLive: (tabId: string) => void;
}

interface CandleKitReplayFollowButtonProps {
  isFollowing: boolean;
  onSnapToLive: () => void;
}

export function CandleKitReplayFollowButton({
  isFollowing,
  onSnapToLive,
}: CandleKitReplayFollowButtonProps) {
  if (isFollowing) return null;
  return (
    <button
      type="button"
      className="backtest-follow-live"
      aria-label="Snap chart to latest candle"
      title="Snap chart to latest candle"
      onClick={onSnapToLive}
    >
      <ChevronsRight className="h-4 w-4" aria-hidden="true" />
      <span className="sr-only">Snap chart to latest candle</span>
    </button>
  );
}

function canonicalDrawingArray(serializedState: string): string {
  try {
    const parsed: unknown = JSON.parse(serializedState);
    return Array.isArray(parsed) ? JSON.stringify(parsed) : '[]';
  } catch {
    return '[]';
  }
}

function getLoadError(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message
    : 'Could not load saved drawings.';
}

function BacktestSimulationChartLayer() {
  const ui = useBacktestSimulationChartUi();
  const { controller } = useChartApi();
  const [, setScaleRevision] = useState(0);

  useEffect(() => {
    const chart = controller.getChart();
    let frame = 0;
    const update = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => setScaleRevision((revision) => revision + 1));
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(update);
    const element = chart.chartElement();
    element.addEventListener('pointermove', update);
    element.addEventListener('wheel', update, { passive: true });
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    observer?.observe(element);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(update);
      element.removeEventListener('pointermove', update);
      element.removeEventListener('wheel', update);
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [controller]);

  if (!ui) return null;
  const series = controller.getSeries();
  const priceToCoordinate = (price: number) => series.priceToCoordinate(price);
  const coordinateToPrice = (y: number) => series.coordinateToPrice(y);

  return (
    <>
      {ui.positions.length > 0 && (
        <BacktestPositionOverlay
          positions={ui.positions}
          pricePrecision={ui.pricePrecision}
          currentClose={ui.currentClose}
          priceToCoordinate={priceToCoordinate}
          coordinateToPrice={coordinateToPrice}
          onMoveStop={ui.onMoveStop}
          onMoveTarget={ui.onMoveTarget}
          onBreakEven={ui.onBreakEven}
          onClose={ui.onClose}
          disabled={ui.disabled}
        />
      )}
      {ui.preview.visible && (
        <BacktestBracketPreview
          {...ui.preview}
          priceToCoordinate={priceToCoordinate}
          coordinateToPrice={coordinateToPrice}
        />
      )}
    </>
  );
}

/** A CandleKit chart with per-run/interval drawings and replay-aware visibility. */
export function CandleKitReplayChart({
  tabId,
  runId,
  intervalMinutes,
  displayTimezone,
  blindMode,
  normalizedReferencePrice,
  cursorTimeMs,
  registerDrawingFlusher,
  onChartReady,
  snapToLive,
}: CandleKitReplayChartProps) {
  const colors = useChartColors();
  const [isFollowing, setIsFollowing] = useState(true);
  const [generation, setGeneration] = useState(0);
  const sessionKey = `${runId}:${intervalMinutes}:${generation}`;
  const [drawingSession, setDrawingSession] = useState<DrawingSession | null>(null);
  const currentSession = drawingSession?.key === sessionKey ? drawingSession : null;
  const engine = currentSession?.engine ?? null;
  const drawingController = currentSession?.controller ?? null;
  const [hydration, setHydration] = useState<HydrationState>({
    key: '',
    status: 'loading',
    error: null,
  });
  const [saveState, setSaveState] = useState<SaveState>({
    key: '',
    status: 'saved',
    error: null,
  });
  const isHydrated = currentSession !== null
    && hydration.key === sessionKey
    && hydration.status === 'ready';
  const loadError = hydration.key === sessionKey && hydration.status === 'error'
    ? hydration.error
    : null;
  const currentSaveState = saveState.key === sessionKey
    ? saveState
    : { key: sessionKey, status: 'saved' as const, error: null };
  const authoritativeStateRef = useRef('[]');
  const visibleIdsRef = useRef<ReadonlySet<string>>(new Set());
  const lastVisibleExportRef = useRef('[]');
  const suppressChangesRef = useRef(false);
  const isHydratedRef = useRef(false);
  const writerRef = useRef<ReturnType<typeof createDrawingStateWriter> | null>(null);
  const cursorTimeRef = useRef(cursorTimeMs);
  cursorTimeRef.current = cursorTimeMs;
  const isMountedRef = useRef(true);
  const chartLifecycleRef = useRef(0);
  const chartUnregisterRef = useRef<(() => void) | null>(null);
  const discardConflictedDraftOnUnmountRef = useRef(false);
  const panelScopeKey = `${runId}:${tabId}`;

  const chartTheme = useMemo<ChartTheme>(() => {
    const preset = colors.isDark ? darkTheme : lightTheme;
    return {
      ...preset,
      background: colors.tooltipBg,
      text: colors.tooltipText,
      grid: colors.grid,
      axis: colors.axisLine,
      crosshair: colors.reference,
      crosshairLabelBg: colors.tooltipBg,
      up: colors.isDark ? '#34d399' : '#16a34a',
      down: colors.isDark ? '#f87171' : '#dc2626',
      line: colors.isDark ? '#60a5fa' : '#2563eb',
      volumeUp: colors.isDark ? 'rgba(52,211,153,0.35)' : 'rgba(34,197,94,0.35)',
      volumeDown: colors.isDark ? 'rgba(248,113,113,0.35)' : 'rgba(239,68,68,0.35)',
    };
  }, [colors]);

  const timeFormatters = useMemo(
    () => createBacktestTimeFormatters(displayTimezone, blindMode),
    [blindMode, displayTimezone]
  );
  const mapDrawingPrices = useCallback((serializedState: string, inverse = false) => {
    if (!blindMode) return serializedState;
    const referencePrice = normalizedReferencePrice;
    if (referencePrice == null || !Number.isFinite(referencePrice) || referencePrice === 0) {
      throw new Error('This Blind run is missing a valid normalized-price reference.');
    }
    return transformDrawingPrices(serializedState, (price) => inverse
      ? price * referencePrice / 100
      : normalizeBacktestPrice(price, referencePrice));
  }, [blindMode, normalizedReferencePrice]);
  const chartOptions = useMemo(() => ({
    localization: { timeFormatter: timeFormatters.timeFormatter },
    timeScale: { tickMarkFormatter: timeFormatters.tickMarkFormatter },
  }), [timeFormatters]);

  const overlayStyle = {
    '--ck-bg': colors.tooltipBg,
    '--ck-fg': colors.tooltipText,
    '--ck-muted': colors.tick,
    '--ck-border': colors.tooltipBorder,
    '--ck-accent': colors.isDark ? '#60a5fa' : '#2563eb',
    '--ck-accent-fg': colors.isDark ? '#111827' : '#ffffff',
    '--ck-up': colors.isDark ? '#34d399' : '#16a34a',
    '--ck-down': colors.isDark ? '#f87171' : '#dc2626',
    '--ck-warn': colors.isDark ? '#fbbf24' : '#d97706',
  } as CSSProperties;

  useEffect(() => {
    let cancelled = false;
    let unsubscribeEngine: (() => void) | null = null;
    let unregisterFlusher: (() => void) | null = null;
    let activeWriter: ReturnType<typeof createDrawingStateWriter> | null = null;
    // CandleKit controllers destroy their engine, so every effect setup owns a fresh pair.
    const sessionEngine = new DrawingEngine();
    const sessionController = new DrawingController({ engine: sessionEngine, storageKey: null });
    const session: DrawingSession = {
      key: sessionKey,
      engine: sessionEngine,
      controller: sessionController,
    };

    isHydratedRef.current = false;
    writerRef.current = null;
    authoritativeStateRef.current = '[]';
    visibleIdsRef.current = new Set();
    lastVisibleExportRef.current = '[]';
    setHydration({ key: sessionKey, status: 'loading', error: null });
    setSaveState({ key: sessionKey, status: 'saved', error: null });

    unsubscribeEngine = sessionEngine.onChange(() => {
      if (!isHydratedRef.current || suppressChangesRef.current) return;
      const visibleExport = sessionEngine.export();
      if (visibleExport === lastVisibleExportRef.current) return;
      const canonicalVisibleExport = mapDrawingPrices(visibleExport, true);

      const authoritative = reconcileVisibleDrawingChanges(
        authoritativeStateRef.current,
        canonicalVisibleExport,
        visibleIdsRef.current
      );
      authoritativeStateRef.current = authoritative;
      const filteredVisible = mapDrawingPrices(canonicalDrawingArray(
        filterDrawingsAtReplayCursor(authoritative, cursorTimeRef.current)
      ));
      if (filteredVisible !== canonicalDrawingArray(visibleExport)) {
        suppressChangesRef.current = true;
        sessionEngine.import(filteredVisible);
        suppressChangesRef.current = false;
      }
      visibleIdsRef.current = new Set(getDrawingIds(filteredVisible));
      lastVisibleExportRef.current = sessionEngine.export();
      setSaveState({ key: sessionKey, status: 'saving', error: null });
      writerRef.current?.enqueue(authoritative);
    });

    async function loadDrawings() {
      try {
        await waitForPendingPanelFlush(panelScopeKey);
        if (cancelled) return;
        const savedState: BacktestDrawingState = await getBacktestDrawingState(
          runId,
          intervalMinutes
        );
        if (cancelled) return;
        if (savedState.interval_minutes !== intervalMinutes) {
          throw new Error('The saved drawings do not match this chart interval.');
        }

        const authoritative = normalizeSerializedDrawingState(savedState.serialized_state);
        const visible = mapDrawingPrices(canonicalDrawingArray(
          filterDrawingsAtReplayCursor(authoritative, cursorTimeRef.current)
        ));
        authoritativeStateRef.current = authoritative;
        visibleIdsRef.current = new Set(getDrawingIds(visible));

        suppressChangesRef.current = true;
        sessionEngine.import(visible);
        lastVisibleExportRef.current = sessionEngine.export();
        suppressChangesRef.current = false;

        activeWriter = createDrawingStateWriter({
          runId,
          intervalMinutes,
          initialRevision: savedState.revision,
          save: saveBacktestDrawingState,
          onConflict: () => {
            if (cancelled) return;
            sessionEngine.setLocked(true);
            setSaveState({
              key: sessionKey,
              status: 'conflict',
              error: 'Another chart saved newer drawings. Reload the saved version before editing again.',
            });
          },
          onError: () => {
            if (cancelled) return;
            setSaveState({
              key: sessionKey,
              status: 'error',
              error: 'Could not save drawing changes. Retry the save before leaving this run.',
            });
          },
          onSaved: () => {
            if (cancelled) return;
            setSaveState({
              key: sessionKey,
              status: activeWriter?.hasPending() ? 'saving' : 'saved',
              error: null,
            });
          },
        });
        writerRef.current = activeWriter;
        unregisterFlusher = registerDrawingFlusher(
          tabId,
          () => activeWriter?.flushAndConfirm()
        );
        isHydratedRef.current = true;
        setDrawingSession(session);
        setHydration({ key: sessionKey, status: 'ready', error: null });
      } catch (error: unknown) {
        suppressChangesRef.current = false;
        if (!cancelled) {
          isHydratedRef.current = false;
          setHydration({ key: sessionKey, status: 'error', error: getLoadError(error) });
        }
      }
    }

    void loadDrawings();

    return () => {
      cancelled = true;
      isHydratedRef.current = false;
      unsubscribeEngine?.();
      unregisterFlusher?.();
      if (writerRef.current === activeWriter) writerRef.current = null;
      if (activeWriter) {
        const outgoingWriter = activeWriter;
        if (
          outgoingWriter.isConflicted()
          && discardConflictedDraftOnUnmountRef.current
        ) {
          discardConflictedDraftOnUnmountRef.current = false;
          discardPendingPanelFlush(panelScopeKey);
        } else {
          void registerPendingPanelFlush(
            panelScopeKey,
            async () => {
              try {
                await outgoingWriter.flushAndConfirm();
              } catch (error: unknown) {
                if (outgoingWriter.isConflicted()) throw error;
                outgoingWriter.enqueue(authoritativeStateRef.current);
                await outgoingWriter.flushAndConfirm();
              }
            }
          ).catch(() => undefined);
        }
      }
      sessionEngine.destroy();
    };
  }, [
    intervalMinutes,
    panelScopeKey,
    registerDrawingFlusher,
    runId,
    sessionKey,
    tabId,
    mapDrawingPrices,
  ]);

  useEffect(() => {
    if (!engine || !isHydratedRef.current || cursorTimeMs === null) return;
    const visible = mapDrawingPrices(canonicalDrawingArray(
      filterDrawingsAtReplayCursor(authoritativeStateRef.current, cursorTimeMs)
    ));
    const nextVisibleIds = new Set(getDrawingIds(visible));
    if (visible !== engine.export()) {
      suppressChangesRef.current = true;
      engine.import(visible);
      suppressChangesRef.current = false;
    }
    visibleIdsRef.current = nextVisibleIds;
    lastVisibleExportRef.current = engine.export();
  }, [cursorTimeMs, engine, isHydrated, mapDrawingPrices]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      chartLifecycleRef.current += 1;
      chartUnregisterRef.current?.();
      chartUnregisterRef.current = null;
    };
  }, []);

  function retrySave() {
    const writer = writerRef.current;
    if (!writer || writer.isConflicted()) return;
    setSaveState({ key: sessionKey, status: 'saving', error: null });
    writer.enqueue(authoritativeStateRef.current);
    void writer.flush();
  }

  function reloadSavedDrawings() {
    void retryPendingPanelFlush(panelScopeKey)
      .then(() => setGeneration((current) => current + 1))
      .catch((error: unknown) => {
        setHydration({
          key: sessionKey,
          status: 'error',
          error: `Could not save the moved chart's drawings: ${getLoadError(error)}`,
        });
      });
  }

  function discardLocalDrawingsAndReload() {
    discardConflictedDraftOnUnmountRef.current = Boolean(
      writerRef.current?.isConflicted()
    );
    discardPendingPanelFlush(panelScopeKey);
    setGeneration((current) => current + 1);
  }

  return (
    <div
      className="backtest-candlekit-chart relative"
      data-testid={`replay-chart-${tabId}`}
      style={overlayStyle}
    >
      <ChartView
        data={EMPTY_DATA}
        theme={chartTheme}
        chartOptions={chartOptions}
        drawing={isHydrated ? drawingController : null}
        showVolume
        autoFit
        className="backtest-candlekit-chart-view"
        style={{ minHeight: 0, height: '100%' }}
        onReady={(api) => {
          const lifecycle = chartLifecycleRef.current;
          queueMicrotask(() => {
            if (isMountedRef.current && chartLifecycleRef.current === lifecycle) {
              chartUnregisterRef.current?.();
              const unregister = onChartReady(tabId, api, setIsFollowing);
              chartUnregisterRef.current = typeof unregister === 'function'
                ? unregister
                : null;
            }
          });
        }}
      >
        {isHydrated && currentSaveState.status !== 'conflict' && (
          <DrawingToolbar className="ck-toolbar backtest-drawing-toolbar" />
        )}
        <BacktestSimulationChartLayer />
      </ChartView>
      <CandleKitReplayFollowButton
        isFollowing={isFollowing}
        onSnapToLive={() => snapToLive(tabId)}
      />
      {!isHydrated && !loadError && (
        <div className="backtest-drawing-status" role="status">
          Loading saved drawings before enabling editing…
        </div>
      )}
      {loadError && (
        <div className="backtest-drawing-status backtest-drawing-status-error">
          <span role="alert">{loadError}</span>
          <button type="button" onClick={reloadSavedDrawings}>Retry save / load drawings</button>
          <button type="button" onClick={discardLocalDrawingsAndReload}>
            Discard local changes and reload saved drawings
          </button>
        </div>
      )}
      {isHydrated && currentSaveState.status !== 'saved' && (
        <div
          className={`backtest-drawing-status ${currentSaveState.status === 'conflict' ? 'backtest-drawing-status-error' : ''}`}
          role={currentSaveState.status === 'conflict' || currentSaveState.status === 'error' ? 'alert' : 'status'}
        >
          <span>
            {currentSaveState.status === 'saving'
              ? 'Saving drawings…'
              : currentSaveState.error}
          </span>
          {currentSaveState.status === 'error' && (
            <button type="button" onClick={retrySave}>Retry save</button>
          )}
          {currentSaveState.status === 'conflict' && (
            <button type="button" onClick={discardLocalDrawingsAndReload}>
              Reload saved drawings (discard local changes)
            </button>
          )}
        </div>
      )}
      <span className="sr-only">
        Drawing state uses CandleKit {CANDLEKIT_VERSION}, schema {DRAWING_SCHEMA_VERSION}.
      </span>
    </div>
  );
}
