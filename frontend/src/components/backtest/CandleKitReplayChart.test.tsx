import { describe, expect, it, vi } from 'vitest';
import type { BacktestCandle } from '../../types/backtest.types';
import { aggregateRevealedCandles } from '../../utils/backtestCandles';
import { CandleKitReplayFollowButton } from './CandleKitReplayChart';

function candle(time_ms: number): BacktestCandle {
  return { time_ms, open: 1, high: 2, low: 0.5, close: 1.5 };
}

describe('CandleKit replay follow control', () => {
  it('provides pre-start candles as chart context at the initial replay cursor', () => {
    const initialChartData = aggregateRevealedCandles(
      [candle(0), candle(60_000), candle(120_000)],
      1,
      1
    );

    expect(initialChartData.map((bar) => bar.ts)).toEqual([0, 60_000]);
  });

  it('is hidden while the pane follows the latest candle', () => {
    expect(CandleKitReplayFollowButton({
      isFollowing: true,
      onSnapToLive: vi.fn(),
    })).toBeNull();
  });

  it('exposes an accessible snap action while the pane is away from the live edge', () => {
    const onSnapToLive = vi.fn();
    const button = CandleKitReplayFollowButton({
      isFollowing: false,
      onSnapToLive,
    });

    expect(button).not.toBeNull();
    if (!button) return;
    expect(button.type).toBe('button');
    expect(button.props['aria-label']).toBe('Snap chart to latest candle');
    button.props.onClick();
    expect(onSnapToLive).toHaveBeenCalledOnce();
  });
});
