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
