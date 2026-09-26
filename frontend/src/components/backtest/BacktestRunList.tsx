import { AlertTriangle, CheckCircle2, Loader2, Play, RefreshCw, X } from 'lucide-react';
import type {
  BacktestPreparationNotice,
  BacktestRunSummary,
} from '../../types/backtest.types';

interface BacktestRunListProps {
  runs: BacktestRunSummary[];
  notices: BacktestPreparationNotice[];
  isLoading: boolean;
  loadError: string | null;
  retryingRunId: string | null;
  dismissingNoticeId: string | null;
  onCreateRun: () => void;
  onRefresh: () => void | Promise<void>;
  onOpenRun: (runId: string) => void;
  onRetryRun: (runId: string) => void | Promise<void>;
  onNoticeAction: (notice: BacktestPreparationNotice) => void;
  onDismissNotice: (noticeId: string) => void | Promise<void>;
}

function formatStage(stage: string): string {
  const words = stage.replace(/[_-]+/g, ' ').trim();
  return words
    ? words.charAt(0).toUpperCase() + words.slice(1)
    : 'Preparing data';
}

function formatNoticeOutcome(outcome: BacktestPreparationNotice['outcome']): string {
  return outcome === 'no_data' ? 'No candle data found' : 'Preparation failed';
}

/** Run cards, progress, and dismissible preparation outcome notices. */
export function BacktestRunList({
  runs,
  notices,
  isLoading,
  loadError,
  retryingRunId,
  dismissingNoticeId,
  onCreateRun,
  onRefresh,
  onOpenRun,
  onRetryRun,
  onNoticeAction,
  onDismissNotice,
}: BacktestRunListProps) {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Backtest Runs</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Prepare one-minute historical candles and open a replay when a run is ready.
          </p>
        </div>
        <button type="button" onClick={onCreateRun} className="btn-primary">
          New run
        </button>
      </div>

      {loadError && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
          {loadError}
          <button
            type="button"
            onClick={() => void onRefresh()}
            className="inline-flex items-center gap-2 font-medium underline underline-offset-2"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      )}

      {notices.length > 0 && (
        <section aria-labelledby="backtest-notices-heading" className="space-y-3">
          <h2 id="backtest-notices-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Preparation results
          </h2>
          {notices.map((notice) => (
            <article
              key={notice.id}
              className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20"
            >
              <div className="flex min-w-0 items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                    {formatNoticeOutcome(notice.outcome)}: {notice.instrument}
                  </h3>
                  <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                    Selected range: {notice.requested_start_date} – {notice.requested_end_date}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => onNoticeAction(notice)}
                  className="btn-secondary text-sm"
                >
                  {notice.next_action === 'edit_range' ? 'Edit range' : 'Start a new run'}
                </button>
                <button
                  type="button"
                  onClick={() => void onDismissNotice(notice.id)}
                  disabled={dismissingNoticeId === notice.id}
                  aria-label={`Dismiss ${notice.instrument} preparation result`}
                  className="rounded-md p-2 text-gray-500 hover:bg-amber-100 hover:text-gray-800 disabled:opacity-50 dark:text-gray-300 dark:hover:bg-amber-900/50 dark:hover:text-white"
                >
                  {dismissingNoticeId === notice.id
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <X className="h-4 w-4" />}
                </button>
              </div>
            </article>
          ))}
        </section>
      )}

      <section aria-labelledby="backtest-runs-heading" className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 id="backtest-runs-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Your runs
          </h2>
          {isLoading && runs.length > 0 && (
            <span className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400" role="status">
              <Loader2 className="h-4 w-4 animate-spin" /> Updating progress
            </span>
          )}
        </div>

        {isLoading && runs.length === 0 ? (
          <div className="card flex items-center justify-center gap-3 p-10 text-sm text-gray-500 dark:text-gray-400" role="status">
            <Loader2 className="h-5 w-5 animate-spin" /> Loading Backtest runs…
          </div>
        ) : runs.length === 0 ? (
          <div className="card flex flex-col items-center gap-3 p-10 text-center">
            <p className="text-sm text-gray-600 dark:text-gray-300">No Backtest runs yet.</p>
            <button type="button" onClick={onCreateRun} className="btn-primary">
              Create your first run
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {runs.map((run) => {
              const isPreparing = run.status === 'preparing';
              const percent = run.progress?.percent;
              const hasMeasuredProgress = typeof percent === 'number' && Number.isFinite(percent);
              const safePercent = hasMeasuredProgress
                ? Math.min(100, Math.max(0, percent))
                : 0;

              return (
                <article key={run.id} className="card space-y-4 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0">
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {run.instrument}
                      </h3>
                      <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                        {run.requested_start_date} – {run.requested_end_date}
                      </p>
                      {run.account_label && (
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          Backtest account: {run.account_label}
                        </p>
                      )}
                    </div>

                    {isPreparing ? (
                      <button
                        type="button"
                        onClick={() => void onRetryRun(run.id)}
                        disabled={retryingRunId === run.id}
                        className="btn-secondary inline-flex items-center gap-2 text-sm disabled:opacity-60"
                      >
                        {retryingRunId === run.id
                          ? <Loader2 className="h-4 w-4 animate-spin" />
                          : <RefreshCw className="h-4 w-4" />}
                        Retry preparation
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onOpenRun(run.id)}
                        className="btn-primary inline-flex items-center gap-2 text-sm"
                      >
                        <Play className="h-4 w-4" /> Open replay
                      </button>
                    )}
                  </div>

                  {isPreparing ? (
                    <div>
                      <div className="mb-2 flex items-center justify-between gap-4 text-sm">
                        <span className="text-gray-700 dark:text-gray-300">
                          {formatStage(run.progress?.stage ?? '')}
                        </span>
                        <span className="shrink-0 text-gray-500 dark:text-gray-400">
                          {hasMeasuredProgress ? `${Math.round(safePercent)}%` : 'Progress unavailable'}
                        </span>
                      </div>
                      <div
                        className="h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700"
                        role="progressbar"
                        aria-label={`Preparation progress for ${run.instrument}`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        {...(hasMeasuredProgress ? { 'aria-valuenow': Math.round(safePercent) } : {})}
                      >
                        <div
                          className={`h-full rounded-full bg-brand-600 transition-all ${hasMeasuredProgress ? '' : 'w-1/3 animate-pulse'}`}
                          style={hasMeasuredProgress ? { width: `${safePercent}%` } : undefined}
                        />
                      </div>
                    </div>
                  ) : (
                    <p className="flex items-center gap-2 text-sm text-green-700 dark:text-green-400">
                      <CheckCircle2 className="h-4 w-4" /> Ready to replay
                    </p>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
