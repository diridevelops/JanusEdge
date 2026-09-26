import { type CSSProperties, useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getBacktestRun, saveBacktestChartTabs } from '../api/backtests.api';
import { BacktestChartTab } from '../components/backtest/BacktestChartTab';
import { BacktestReplayControls } from '../components/backtest/BacktestReplayControls';
import {
  BacktestSyncControls,
  type BacktestSyncOptions,
} from '../components/backtest/BacktestSyncControls';
import { Spinner } from '../components/ui/Spinner';
import { useBacktestChartSync } from '../hooks/useBacktestChartSync';
import { useBacktestReplay } from '../hooks/useBacktestReplay';
import { useChartColors } from '../hooks/useChartColors';
import type { BacktestChartTab as BacktestChartTabConfig, BacktestRunDetail } from '../types/backtest.types';
import '../styles/backtest-candlekit.css';

function normalizeTabs(tabs: readonly BacktestChartTabConfig[]): BacktestChartTabConfig[] {
  return [...tabs]
    .sort((left, right) => left.position - right.position)
    .map((tab, position) => ({ ...tab, position }));
}

function formatTimestamp(timeMs: number, timezone: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone || 'UTC',
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
      timeZoneName: 'short',
    }).format(new Date(timeMs));
  } catch {
    return new Date(timeMs).toISOString();
  }
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return 'Could not load this Backtest run.';
}

/** Fetch the selected ready run; preparing runs remain on the run-list route. */
export function BacktestReplayPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<BacktestRunDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!runId) {
      setIsLoading(false);
      setLoadError('The Backtest run id is missing.');
      return () => { cancelled = true; };
    }

    setIsLoading(true);
    setLoadError(null);
    void getBacktestRun(runId)
      .then((detail) => {
        if (!cancelled) setRun(detail);
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(getErrorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => { cancelled = true; };
  }, [attempt, runId]);

  if (isLoading) {
    return (
      <div className="flex min-h-64 items-center justify-center" aria-label="Loading Backtest run">
        <Spinner />
      </div>
    );
  }

  if (loadError || !run) {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-red-200 bg-white p-6 dark:border-red-900 dark:bg-gray-900">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Replay unavailable</h1>
        <p className="mt-2 text-sm text-red-700 dark:text-red-300" role="alert">
          {loadError ?? 'Could not find this Backtest run.'}
        </p>
        <div className="mt-4 flex gap-3">
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
            className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Retry
          </button>
          <Link to="/backtest/runs" className="rounded-md px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800">
            Back to runs
          </Link>
        </div>
      </section>
    );
  }

  if (run.status !== 'ready') {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Run is still preparing</h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
          Replay charts are available after preparation completes.
        </p>
        <Link to="/backtest/runs" className="mt-4 inline-flex rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700">
          View run progress
        </Link>
      </section>
    );
  }

  return <BacktestReplayRunView key={run.id} run={run} />;
}

function BacktestReplayRunView({ run }: { run: BacktestRunDetail }) {
  const colors = useChartColors();
  const [tabs, setTabs] = useState<BacktestChartTabConfig[]>(() => normalizeTabs(
    run.tabs.length > 0
      ? run.tabs
      : [{ id: 'chart-1', position: 0, interval_minutes: 1 }]
  ));
  const [tabSaveError, setTabSaveError] = useState<string | null>(null);
  const savedTabsRef = useRef(tabs);
  const pendingTabsRef = useRef<BacktestChartTabConfig[] | null>(null);
  const tabSaveInProgressRef = useRef(false);
  const replay = useBacktestReplay(run, tabs);
  const chartSync = useBacktestChartSync(tabs, run.instrument, replay.controller);

  const saveTabs = useCallback((nextTabs: BacktestChartTabConfig[]) => {
    const normalized = normalizeTabs(nextTabs);
    setTabs(normalized);
    pendingTabsRef.current = normalized;

    async function drainTabSaves() {
      if (tabSaveInProgressRef.current) return;
      tabSaveInProgressRef.current = true;
      while (pendingTabsRef.current) {
        const desired = pendingTabsRef.current;
        pendingTabsRef.current = null;
        try {
          const saved = normalizeTabs(await saveBacktestChartTabs(run.id, desired));
          savedTabsRef.current = saved;
          setTabSaveError(null);
          if (!pendingTabsRef.current) setTabs(saved);
        } catch {
          setTabSaveError('Could not save chart tabs. Your last saved configuration is still available.');
          if (!pendingTabsRef.current) {
            setTabs(savedTabsRef.current);
            break;
          }
        }
      }
      tabSaveInProgressRef.current = false;
      if (pendingTabsRef.current) void drainTabSaves();
    }

    void drainTabSaves();
  }, [run.id]);

  const handleIntervalChange = useCallback((tabId: string, intervalMinutes: number) => {
    saveTabs(tabs.map((tab) => (
      tab.id === tabId ? { ...tab, interval_minutes: intervalMinutes } : tab
    )));
  }, [saveTabs, tabs]);

  const handleAddTab = useCallback(() => {
    const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `chart-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    saveTabs([...tabs, { id, position: tabs.length, interval_minutes: 1 }]);
  }, [saveTabs, tabs]);

  const handleRemoveTab = useCallback((tabId: string) => {
    if (tabs.length <= 1) return;
    saveTabs(tabs.filter((tab) => tab.id !== tabId));
  }, [saveTabs, tabs]);

  const setSyncOptions = chartSync.setOptions;
  const registerSyncChart = chartSync.registerChart;
  const unregisterSyncChart = chartSync.unregisterChart;
  const registerReplayChart = replay.registerTabChart;
  const handleSyncChange = useCallback((options: BacktestSyncOptions) => {
    setSyncOptions(options);
  }, [setSyncOptions]);

  const handleChartReady = useCallback((tabId: string, api: import('@getcandlekit/charts/react').ChartViewApi) => {
    registerReplayChart(tabId, api.controller);
    registerSyncChart(tabId, api.controller);
  }, [registerReplayChart, registerSyncChart]);

  const handleChartDispose = useCallback((tabId: string) => {
    registerReplayChart(tabId, null);
    unregisterSyncChart(tabId);
  }, [registerReplayChart, unregisterSyncChart]);

  const firstTimeMs = run.snapshot?.first_time_ms ?? run.coverage?.first_time_ms;
  const lastTimeMs = run.snapshot?.last_time_ms ?? run.coverage?.last_time_ms;
  const timezone = run.display_timezone || 'UTC';
  const chartOverlayStyle = {
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

  return (
    <div className="backtest-candlekit mx-auto max-w-[1800px] space-y-5" style={chartOverlayStyle}>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/backtest/runs" className="text-sm font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400">
            ← Backtest runs
          </Link>
          <h1 className="mt-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
            {run.instrument} replay
          </h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
            {run.requested_start_date} to {run.requested_end_date} · {run.account_label}
          </p>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Display timezone: {timezone}
            {firstTimeMs !== undefined && lastTimeMs !== undefined && (
              <> · Data: {formatTimestamp(firstTimeMs, timezone)} — {formatTimestamp(lastTimeMs, timezone)}</>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={handleAddTab}
          disabled={replay.status !== 'ready'}
          className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
        >
          Add chart
        </button>
      </header>

      {replay.status === 'loading' && (
        <section className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-5 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300" role="status">
          <Spinner />
          Loading the immutable candle snapshot and restoring the saved replay cursor…
        </section>
      )}

      {replay.status === 'error' && (
        <section className="rounded-xl border border-red-200 bg-white p-5 dark:border-red-900 dark:bg-gray-900">
          <p className="text-sm text-red-700 dark:text-red-300" role="alert">
            {replay.error ?? 'Could not load this replay.'}
          </p>
          <button
            type="button"
            onClick={replay.retryLoad}
            className="mt-3 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Retry replay load
          </button>
        </section>
      )}

      {replay.cursorSaveError && (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200" role="alert">
          {replay.cursorSaveError}
        </p>
      )}

      {tabSaveError && (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200" role="alert">
          {tabSaveError}
        </p>
      )}

      {replay.status === 'ready' && replay.controlsController && (
        <>
          <BacktestReplayControls
            controller={replay.controlsController}
            displayTimezone={timezone}
          />
          <BacktestSyncControls options={chartSync.options} onChange={handleSyncChange} />
          <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
            {tabs.map((tab) => (
              <BacktestChartTab
                key={tab.id}
                runId={run.id}
                tab={tab}
                totalTabs={tabs.length}
                cursorTimeMs={replay.cursorTimeMs ?? run.replay_cursor?.time_ms ?? firstTimeMs ?? 0}
                registerDrawingFlusher={replay.registerDrawingFlusher}
                onIntervalChange={handleIntervalChange}
                onRemove={handleRemoveTab}
                onChartReady={handleChartReady}
                onChartDispose={handleChartDispose}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
