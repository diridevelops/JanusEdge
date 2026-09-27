import { type CSSProperties, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getBacktestChartWorkspace, getBacktestRun, saveBacktestChartWorkspace } from '../api/backtests.api';
import { BacktestChartWorkspace } from '../components/backtest/BacktestChartWorkspace';
import { Spinner } from '../components/ui/Spinner';
import { useBacktestChartSync } from '../hooks/useBacktestChartSync';
import { useBacktestReplay } from '../hooks/useBacktestReplay';
import { useAuth } from '../hooks/useAuth';
import { useChartColors } from '../hooks/useChartColors';
import type { BacktestChartTab, BacktestRunDetail } from '../types/backtest.types';
import {
  extractBacktestWorkspaceTabs,
  initializeBacktestWorkspace,
  type BacktestWorkspaceApi,
} from '../utils/backtestWorkspace';
import type { WorkspaceLayout } from '@getcandlekit/charts/react/workspace';
import '../styles/backtest-candlekit.css';

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
  const api = useMemo<BacktestWorkspaceApi>(() => ({
    get: getBacktestChartWorkspace,
    save: saveBacktestChartWorkspace,
  }), []);
  const [workspace, setWorkspace] = useState<{
    layout: WorkspaceLayout;
    revision: number;
  } | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setWorkspace(null);
    setWorkspaceError(null);
    void initializeBacktestWorkspace(run.id, api)
      .then((initialized) => {
        if (!cancelled) setWorkspace(initialized);
      })
      .catch((error: unknown) => {
        if (!cancelled) setWorkspaceError(getErrorMessage(error));
      });
    return () => { cancelled = true; };
  }, [api, loadAttempt, run.id]);

  if (workspaceError) {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-red-200 bg-white p-6 dark:border-red-900 dark:bg-gray-900">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Chart workspace unavailable</h1>
        <p className="mt-2 text-sm text-red-700 dark:text-red-300" role="alert">{workspaceError}</p>
        <button
          type="button"
          onClick={() => setLoadAttempt((value) => value + 1)}
          className="mt-4 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Retry workspace load
        </button>
      </section>
    );
  }

  if (!workspace) {
    return (
      <div className="flex min-h-64 items-center justify-center gap-3 text-sm text-gray-600 dark:text-gray-300" aria-label="Loading chart workspace">
        <Spinner />
        Loading the saved chart workspace…
      </div>
    );
  }

  return (
    <BacktestReplayWorkspaceRun
      run={run}
      initialLayout={workspace.layout}
      revision={workspace.revision}
    />
  );
}

function BacktestReplayWorkspaceRun({
  run,
  initialLayout,
  revision,
}: {
  run: BacktestRunDetail;
  initialLayout: WorkspaceLayout;
  revision: number;
}) {
  const colors = useChartColors();
  const { user } = useAuth();
  const [tabs, setTabs] = useState<BacktestChartTab[]>(() => (
    extractBacktestWorkspaceTabs(initialLayout)
  ));
  const replay = useBacktestReplay(run, tabs);
  const chartSync = useBacktestChartSync(tabs, run.instrument, replay.controller);

  const handleWorkspaceTabsChange = useCallback((nextTabs: BacktestChartTab[]) => {
    setTabs(nextTabs);
  }, []);
  const registerSyncChart = chartSync.registerChart;
  const registerReplayChart = replay.registerTabChart;

  const handleChartReady = useCallback((
    tabId: string,
    api: import('@getcandlekit/charts/react').ChartViewApi,
    onFollowStateChange: (isFollowing: boolean) => void
  ) => {
    const unregisterReplay = registerReplayChart(tabId, api.controller);
    const unregisterSync = registerSyncChart(tabId, api.controller, onFollowStateChange);
    return () => {
      unregisterSync();
      if (unregisterReplay) unregisterReplay();
    };
  }, [registerReplayChart, registerSyncChart]);

  const firstTimeMs = run.snapshot?.first_time_ms ?? run.coverage?.first_time_ms;
  const timezone = user?.display_timezone
    || user?.timezone
    || run.display_timezone
    || 'UTC';
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
    <div className="backtest-candlekit mx-auto max-w-[1800px] space-y-4" style={chartOverlayStyle}>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="sr-only">{run.instrument} replay</h1>
          <Link to="/backtest/runs" className="text-sm font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400">
            ← Backtest runs
          </Link>
        </div>
      </header>

      {replay.status === 'loading' && (
        <section className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-5 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900" role="status">
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

      {replay.status === 'ready' && replay.controlsController && (
        <BacktestChartWorkspace
          run={run}
          replayController={replay.controlsController}
          displayTimezone={timezone}
          initialLayout={initialLayout}
          revision={revision}
          cursorTimeMs={replay.cursorTimeMs ?? run.replay_cursor?.time_ms ?? firstTimeMs ?? 0}
          registerDrawingFlusher={replay.registerDrawingFlusher}
          onChartReady={handleChartReady}
          snapToLive={chartSync.snapToLive}
          onTabsChange={handleWorkspaceTabsChange}
        />
      )}
    </div>
  );
}
