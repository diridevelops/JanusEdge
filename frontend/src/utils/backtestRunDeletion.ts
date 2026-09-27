import type { BacktestRunSummary } from '../types/backtest.types';

/** Format the explicit, owner-visible scope before any delete request begins. */
export function getBacktestRunDeletionConfirmation(
  run: BacktestRunSummary
): string {
  return [
    `Permanently delete the ${run.instrument} Backtest run?`,
    `Selected range: ${run.requested_start_date} through ${run.requested_end_date}.`,
    `Dedicated account: ${run.account_label || run.account_id}.`,
    'This also permanently removes the account, all linked trades, and the run’s stored replay data.',
  ].join('\n\n');
}

export function confirmBacktestRunDeletion(
  run: BacktestRunSummary,
  confirmAction: (message: string) => boolean = (message) =>
    window.confirm(message)
): boolean {
  return confirmAction(getBacktestRunDeletionConfirmation(run));
}
