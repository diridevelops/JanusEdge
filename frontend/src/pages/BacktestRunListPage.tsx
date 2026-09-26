import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  dismissBacktestNotice,
  listBacktestNotices,
  listBacktestRuns,
  retryBacktestRun,
} from '../api/backtests.api';
import { BacktestRunForm, type BacktestRunFormValues } from '../components/backtest/BacktestRunForm';
import { BacktestRunList } from '../components/backtest/BacktestRunList';
import { useAuth } from '../hooks/useAuth';
import type {
  BacktestPreparationNotice,
  BacktestRunSummary,
} from '../types/backtest.types';

/** Lists Backtest runs and polls worker progress while a run is preparing. */
export function BacktestRunListPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [runs, setRuns] = useState<BacktestRunSummary[]>([]);
  const [notices, setNotices] = useState<BacktestPreparationNotice[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null);
  const [dismissingNoticeId, setDismissingNoticeId] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [formInitialValues, setFormInitialValues] = useState<Partial<BacktestRunFormValues>>();
  const [formSeed, setFormSeed] = useState(0);
  const isMountedRef = useRef(false);
  const requestInFlightRef = useRef(false);
  const queuedRefreshRef = useRef(false);
  const queuedShowLoadingRef = useRef(false);

  const refresh = useCallback(async (showLoading = false) => {
    if (showLoading) setIsLoading(true);
    if (requestInFlightRef.current) {
      queuedRefreshRef.current = true;
      queuedShowLoadingRef.current ||= showLoading;
      return;
    }
    requestInFlightRef.current = true;

    try {
      const [nextRuns, nextNotices] = await Promise.all([
        listBacktestRuns(),
        listBacktestNotices(),
      ]);
      if (isMountedRef.current) {
        setRuns(nextRuns);
        setNotices(nextNotices);
        setLoadError(null);
      }
    } catch {
      if (isMountedRef.current) {
        setLoadError('Could not load Backtest runs. Try refreshing the list.');
      }
    } finally {
      requestInFlightRef.current = false;
      if (showLoading && isMountedRef.current) setIsLoading(false);
      if (queuedRefreshRef.current && isMountedRef.current) {
        const shouldShowLoading = queuedShowLoadingRef.current;
        queuedRefreshRef.current = false;
        queuedShowLoadingRef.current = false;
        void refresh(shouldShowLoading);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    void refresh(true);
    return () => {
      isMountedRef.current = false;
    };
  }, [refresh]);

  const hasPreparingRun = runs.some((run) => run.status === 'preparing');
  useEffect(() => {
    if (!hasPreparingRun) return;

    const intervalId = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [hasPreparingRun, refresh]);

  function openNewRunForm() {
    setFormInitialValues(undefined);
    setFormSeed((seed) => seed + 1);
    setIsFormOpen(true);
  }

  function openNoticeAction(notice: BacktestPreparationNotice) {
    setFormInitialValues({
      instrument: notice.instrument,
      startDate: notice.requested_start_date,
      endDate: notice.requested_end_date,
    });
    setFormSeed((seed) => seed + 1);
    setIsFormOpen(true);
  }

  async function handleRunCreated() {
    setIsFormOpen(false);
    setFormInitialValues(undefined);
    await refresh();
  }

  async function handleRetryRun(runId: string) {
    setRetryingRunId(runId);
    setLoadError(null);
    try {
      await retryBacktestRun(runId);
      await refresh();
    } catch {
      setLoadError('Could not retry this preparation. Refresh the list and try again.');
    } finally {
      setRetryingRunId(null);
    }
  }

  async function handleDismissNotice(noticeId: string) {
    setDismissingNoticeId(noticeId);
    try {
      await dismissBacktestNotice(noticeId);
      setNotices((current) => current.filter((notice) => notice.id !== noticeId));
    } catch {
      setLoadError('Could not dismiss this preparation result. Try again.');
    } finally {
      setDismissingNoticeId(null);
    }
  }

  const displayTimezone = user?.display_timezone || user?.timezone || '';

  return (
    <div className="space-y-6">
      {isFormOpen && (
        <div className="mx-auto max-w-5xl">
          <BacktestRunForm
            key={formSeed}
            displayTimezone={displayTimezone}
            initialValues={formInitialValues}
            onCancel={() => setIsFormOpen(false)}
            onCreated={handleRunCreated}
          />
        </div>
      )}
      <BacktestRunList
        runs={runs}
        notices={notices}
        isLoading={isLoading}
        loadError={loadError}
        retryingRunId={retryingRunId}
        dismissingNoticeId={dismissingNoticeId}
        onCreateRun={openNewRunForm}
        onRefresh={() => refresh(true)}
        onOpenRun={(runId) => navigate(`/backtest/runs/${encodeURIComponent(runId)}/replay`)}
        onRetryRun={handleRetryRun}
        onNoticeAction={openNoticeAction}
        onDismissNotice={handleDismissNotice}
      />
    </div>
  );
}
