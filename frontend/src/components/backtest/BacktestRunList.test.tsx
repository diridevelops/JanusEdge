import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { BacktestRunList } from './BacktestRunList';
import type { BacktestRunSummary } from '../../types/backtest.types';
import { confirmBacktestRunDeletion } from '../../utils/backtestRunDeletion';

const run: BacktestRunSummary = {
  id: 'run-1',
  instrument: 'EUR-USD',
  requested_start_date: '2026-01-05',
  requested_end_date: '2026-01-06',
  display_timezone: 'UTC',
  status: 'ready',
  account_id: 'account-1',
  account_label: 'Backtest EUR-USD run-1',
  progress: { stage: 'complete', percent: 100 },
  created_at: '2026-01-01T00:00:00Z',
};

const blindRun: BacktestRunSummary = {
  ...run,
  blind_mode: true,
  account_label: 'Backtest EUR-USD blind',
};

describe('Backtest run deletion controls', () => {
  it('asks for explicit confirmation with the run, account, and trade scope', () => {
    let confirmationText = '';
    const confirm = vi.fn((message: string) => {
      confirmationText = message;
      return true;
    });

    expect(confirmBacktestRunDeletion(run, confirm)).toBe(true);
    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('EUR-USD')
    );
    expect(confirmationText).toContain('2026-01-05');
    expect(confirmationText).toContain('2026-01-06');
    expect(confirmationText).toContain(run.account_label);
    expect(confirmationText).toContain('all linked trades');
    expect(confirmationText).toContain('permanently');
  });

  it('keeps cancellation non-mutating', () => {
    const confirm = vi.fn<(message: string) => boolean>(() => false);
    const onDeleteRun = vi.fn();

    if (confirmBacktestRunDeletion(run, confirm)) {
      onDeleteRun(run.id);
    }

    expect(onDeleteRun).not.toHaveBeenCalled();
  });

  it('shows pending cleanup and does not offer replay or another delete', () => {
    const pendingRun = { ...run, status: 'deleting' as const };
    const html = renderToStaticMarkup(
      <BacktestRunList
        runs={[pendingRun]}
        notices={[]}
        isLoading={false}
        loadError={null}
        retryingRunId={null}
        deletingRunId={null}
        dismissingNoticeId={null}
        onCreateRun={() => undefined}
        onRefresh={() => undefined}
        onOpenRun={() => undefined}
        onRetryRun={() => undefined}
        onDeleteRun={() => undefined}
        onNoticeAction={() => undefined}
        onDismissNotice={() => undefined}
      />
    );

    expect(html).toContain('Deletion in progress');
    expect(html).not.toContain('Open replay');
    expect(html).not.toContain('Delete run');
  });

  it('shows instrument and selection status until a random period is resolved', () => {
    const selectingRun: BacktestRunSummary = {
      ...run,
      requested_start_date: null,
      requested_end_date: null,
      account_id: null,
      account_label: null,
      period_selection: 'random',
      period_months: 3,
      status: 'selecting_period',
      progress: { stage: 'selecting_period', percent: null },
    };
    const html = renderToStaticMarkup(
      <BacktestRunList
        runs={[selectingRun]}
        notices={[]}
        isLoading={false}
        loadError={null}
        retryingRunId={null}
        deletingRunId={null}
        dismissingNoticeId={null}
        onCreateRun={() => undefined}
        onRefresh={() => undefined}
        onOpenRun={() => undefined}
        onRetryRun={() => undefined}
        onDeleteRun={() => undefined}
        onNoticeAction={() => undefined}
        onDismissNotice={() => undefined}
      />
    );

    expect(html).toContain('EUR-USD');
    expect(html).toContain('Selecting a random 3-month period');
    expect(html).not.toContain('null – null');
    expect(html).not.toContain('Backtest account:');
    expect(html).not.toContain('Open replay');
  });

  it('shows a dismissible random-search failure with instrument and duration', () => {
    const html = renderToStaticMarkup(
      <BacktestRunList
        runs={[]}
        notices={[{
          id: 'notice-1',
          instrument: 'EUR-USD',
          requested_start_date: null,
          requested_end_date: null,
          period_selection: 'random',
          period_months: 6,
          outcome: 'no_data',
          next_action: 'start_new_run',
          message: 'No start date with candles was found for a 6-month period.',
          created_at: '2026-01-01T00:00:00Z',
        }]}
        isLoading={false}
        loadError={null}
        retryingRunId={null}
        deletingRunId={null}
        dismissingNoticeId={null}
        onCreateRun={() => undefined}
        onRefresh={() => undefined}
        onOpenRun={() => undefined}
        onRetryRun={() => undefined}
        onDeleteRun={() => undefined}
        onNoticeAction={() => undefined}
        onDismissNotice={() => undefined}
      />
    );

    expect(html).toContain('EUR-USD');
    expect(html).toContain('6-month random period');
    expect(html).toContain('No start date with candles was found');
    expect(html).toContain('Start a new run');
    expect(html).toContain('Dismiss EUR-USD preparation result');
    expect(html).not.toContain('Selected range: –');
  });

  it('shows list loading errors and exposes the refresh action', () => {
    const html = renderToStaticMarkup(
      <BacktestRunList
        runs={[]}
        notices={[]}
        isLoading={false}
        loadError="Could not load Backtest runs. Try refreshing the list."
        retryingRunId={null}
        deletingRunId={null}
        dismissingNoticeId={null}
        onCreateRun={() => undefined}
        onRefresh={() => undefined}
        onOpenRun={() => undefined}
        onRetryRun={() => undefined}
        onDeleteRun={() => undefined}
        onNoticeAction={() => undefined}
        onDismissNotice={() => undefined}
      />
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain('Could not load Backtest runs');
    expect(html).toContain('Refresh');
  });
});

describe('Blind Backtest run display', () => {
  it('omits dates from blind run deletion confirmation', () => {
    let confirmationText = '';
    confirmBacktestRunDeletion(blindRun, (message) => {
      confirmationText = message;
      return false;
    });

    expect(confirmationText).toContain('EUR-USD');
    expect(confirmationText).not.toContain('2026-01-05');
    expect(confirmationText).not.toContain('2026-01-06');
  });

  it('hides legacy dates in blind account labels', () => {
    const legacyBlindRun = {
      ...blindRun,
      account_label: 'Backtest EUR-USD 2026-01-05 to 2026-01-06 (old-account-id)',
    };
    const html = renderToStaticMarkup(
      <BacktestRunList
        runs={[legacyBlindRun]}
        notices={[]}
        isLoading={false}
        loadError={null}
        retryingRunId={null}
        deletingRunId={null}
        dismissingNoticeId={null}
        onCreateRun={() => undefined}
        onRefresh={() => undefined}
        onOpenRun={() => undefined}
        onRetryRun={() => undefined}
        onDeleteRun={() => undefined}
        onNoticeAction={() => undefined}
        onDismissNotice={() => undefined}
      />
    );

    expect(html).toContain('Backtest EUR-USD blind');
    expect(html).not.toContain('2026-01-05');
    expect(html).not.toContain('2026-01-06');
    expect(html).not.toContain('old-account-id');
  });

  it('hides blind dates in dismissible preparation notices', () => {
    const html = renderToStaticMarkup(
      <BacktestRunList
        runs={[]}
        notices={[{
          id: 'blind-notice',
          instrument: 'EUR-USD',
          requested_start_date: '2026-01-05',
          requested_end_date: '2026-01-06',
          blind_mode: true,
          period_selection: 'random',
          period_months: 1,
          outcome: 'failed',
          next_action: 'start_new_run',
          message: 'Preparation failed.',
          created_at: '2026-01-07T00:00:00Z',
        }]}
        isLoading={false}
        loadError={null}
        retryingRunId={null}
        deletingRunId={null}
        dismissingNoticeId={null}
        onCreateRun={() => undefined}
        onRefresh={() => undefined}
        onOpenRun={() => undefined}
        onRetryRun={() => undefined}
        onDeleteRun={() => undefined}
        onNoticeAction={() => undefined}
        onDismissNotice={() => undefined}
      />
    );

    expect(html).toContain('EUR-USD');
    expect(html).not.toContain('2026-01-05');
    expect(html).not.toContain('2026-01-06');
  });
});
