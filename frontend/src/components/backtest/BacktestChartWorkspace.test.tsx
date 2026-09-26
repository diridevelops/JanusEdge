import { describe, expect, it } from 'vitest';
import {
  discardPendingPanelFlush,
  registerPanelSubscription,
  registerPendingPanelFlush,
  waitForPendingPanelFlush,
} from '../../utils/backtestPanelLifecycle';

describe('Backtest chart panel remount lifecycle', () => {
  it('waits for the pending drawing write before hydrating the moved panel', async () => {
    let finishSave!: () => void;
    let hydrated = false;
    const outgoingSave = registerPendingPanelFlush(
      'run-1:chart-1',
      () => new Promise<void>((resolve) => { finishSave = resolve; })
    );
    const incomingHydration = waitForPendingPanelFlush('run-1:chart-1')
      .then(() => { hydrated = true; });

    await Promise.resolve();
    expect(hydrated).toBe(false);
    finishSave();
    await Promise.all([outgoingSave, incomingHydration]);

    expect(hydrated).toBe(true);
  });

  it('allows an explicit discard to release a failed drawing-save gate', async () => {
    const scope = 'run-1:conflicted-chart';
    await expect(registerPendingPanelFlush(
      scope,
      () => Promise.reject(new Error('revision conflict'))
    )).rejects.toThrow('revision conflict');
    await expect(waitForPendingPanelFlush(scope)).rejects.toThrow('revision conflict');

    discardPendingPanelFlush(scope);
    await expect(waitForPendingPanelFlush(scope)).resolves.toBeUndefined();
  });

  it('detaches each chart listener once and protects a replacement registration', () => {
    const subscriptions = new Map<string, () => void>();
    let detachedCount = 0;
    const disposeOld = registerPanelSubscription(
      subscriptions,
      'chart-1',
      () => { detachedCount += 1; }
    );
    const disposeNew = registerPanelSubscription(
      subscriptions,
      'chart-1',
      () => { detachedCount += 1; }
    );

    expect(detachedCount).toBe(1);
    disposeOld();
    expect(detachedCount).toBe(1);
    expect(subscriptions.get('chart-1')).toBe(disposeNew);

    disposeNew();
    disposeNew();
    expect(detachedCount).toBe(2);
    expect(subscriptions.has('chart-1')).toBe(false);
  });
});
