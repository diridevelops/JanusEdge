import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { ReplayController } from '@getcandlekit/charts/react';
import { BacktestReplayControls } from './BacktestReplayControls';

vi.mock('@getcandlekit/charts/react', () => ({
  ReplayControls: () => null,
}));

describe('Backtest replay controls', () => {
  const controller = {} as ReplayController;

  it('shows an enabled return-to-latest button while behind the persisted cursor', () => {
    const html = renderToStaticMarkup(
      <BacktestReplayControls
        controller={controller}
        displayTimezone="UTC"
        blindMode={false}
        latestTimeMs={120_000}
        isAtLatest={false}
      />
    );

    expect(html).toMatch(/<button[^>]*class="backtest-replay-return-latest"[^>]*>Return to latest<\/button>/);
    expect(html).not.toMatch(/class="backtest-replay-return-latest"[^>]*disabled=""/);
  });

  it('disables return-to-latest when already at the latest candle or navigation is busy', () => {
    const atLatest = renderToStaticMarkup(
      <BacktestReplayControls
        controller={controller}
        displayTimezone="UTC"
        blindMode={false}
        latestTimeMs={120_000}
        isAtLatest
      />
    );
    const busy = renderToStaticMarkup(
      <BacktestReplayControls
        controller={controller}
        displayTimezone="UTC"
        blindMode={false}
        latestTimeMs={120_000}
        isAtLatest={false}
        navigationDisabled
      />
    );

    expect(atLatest).toMatch(/class="backtest-replay-return-latest"[^>]*disabled=""/);
    expect(busy).toMatch(/class="backtest-replay-return-latest"[^>]*disabled=""/);
  });
});
