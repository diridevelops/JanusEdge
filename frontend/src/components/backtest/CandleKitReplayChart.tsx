import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
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
  reconcileVisibleDrawingChanges,
} from '../../utils/backtestDrawings';

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
  cursorTimeMs: number;
  registerDrawingFlusher: (
    tabId: string,
    flush: () => Promise<void> | void
  ) => () => void;
  onChartReady: (tabId: string, api: ChartViewApi) => void;
  onChartDispose: (tabId: string) => void;
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

/** A CandleKit chart with per-run/interval drawings and replay-aware visibility. */
export function CandleKitReplayChart({
  tabId,
  runId,
  intervalMinutes,
  cursorTimeMs,
  registerDrawingFlusher,
  onChartReady,
  onChartDispose,
}: CandleKitReplayChartProps) {
  const colors = useChartColors();
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

      const authoritative = reconcileVisibleDrawingChanges(
        authoritativeStateRef.current,
        visibleExport,
        visibleIdsRef.current
      );
      authoritativeStateRef.current = authoritative;
      const filteredVisible = canonicalDrawingArray(
        filterDrawingsAtReplayCursor(authoritative, cursorTimeRef.current)
      );
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
        const savedState: BacktestDrawingState = await getBacktestDrawingState(
          runId,
          intervalMinutes
        );
        if (cancelled) return;
        if (savedState.interval_minutes !== intervalMinutes) {
          throw new Error('The saved drawings do not match this chart interval.');
        }

        const authoritative = normalizeSerializedDrawingState(savedState.serialized_state);
        const visible = canonicalDrawingArray(
          filterDrawingsAtReplayCursor(authoritative, cursorTimeRef.current)
        );
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
        unregisterFlusher = registerDrawingFlusher(tabId, () => activeWriter?.flush());
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
      void activeWriter?.flush();
      sessionEngine.destroy();
    };
  }, [
    intervalMinutes,
    registerDrawingFlusher,
    runId,
    sessionKey,
    tabId,
  ]);

  useEffect(() => {
    if (!engine || !isHydratedRef.current || cursorTimeMs === null) return;
    const visible = canonicalDrawingArray(
      filterDrawingsAtReplayCursor(authoritativeStateRef.current, cursorTimeMs)
    );
    const nextVisibleIds = new Set(getDrawingIds(visible));
    if (visible !== engine.export()) {
      suppressChangesRef.current = true;
      engine.import(visible);
      suppressChangesRef.current = false;
    }
    visibleIdsRef.current = nextVisibleIds;
    lastVisibleExportRef.current = engine.export();
  }, [cursorTimeMs, engine, isHydrated]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      chartLifecycleRef.current += 1;
      onChartDispose(tabId);
    };
  }, [onChartDispose, tabId]);

  function retrySave() {
    const writer = writerRef.current;
    if (!writer || writer.isConflicted()) return;
    setSaveState({ key: sessionKey, status: 'saving', error: null });
    writer.enqueue(authoritativeStateRef.current);
    void writer.flush();
  }

  function reloadSavedDrawings() {
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
        drawing={isHydrated ? drawingController : null}
        showVolume
        autoFit
        className="backtest-candlekit-chart-view"
        style={{ minHeight: 310, height: '100%' }}
        onReady={(api) => {
          const lifecycle = chartLifecycleRef.current;
          queueMicrotask(() => {
            if (isMountedRef.current && chartLifecycleRef.current === lifecycle) {
              onChartReady(tabId, api);
            }
          });
        }}
      >
        {isHydrated && currentSaveState.status !== 'conflict' && (
          <>
            <DrawingToolbar className="ck-toolbar backtest-drawing-toolbar" />
            <div className="backtest-drawing-hint" aria-label="Drawing editing instructions">
              Select a drawing to move or reshape it. Press Delete to remove the selection.
            </div>
          </>
        )}
      </ChartView>
      {!isHydrated && !loadError && (
        <div className="backtest-drawing-status" role="status">
          Loading saved drawings before enabling editing…
        </div>
      )}
      {loadError && (
        <div className="backtest-drawing-status backtest-drawing-status-error">
          <span role="alert">{loadError}</span>
          <button type="button" onClick={reloadSavedDrawings}>Retry loading drawings</button>
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
            <button type="button" onClick={reloadSavedDrawings}>
              Reload saved drawings (discard local changes)
            </button>
          )}
        </div>
      )}
      {isHydrated && currentSaveState.status === 'saved' && (
        <div className="backtest-drawing-saved" role="status">Drawings saved</div>
      )}
      <span className="sr-only">
        Drawing state uses CandleKit {CANDLEKIT_VERSION}, schema {DRAWING_SCHEMA_VERSION}.
      </span>
    </div>
  );
}
