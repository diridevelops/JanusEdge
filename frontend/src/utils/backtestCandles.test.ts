import { describe, expect, it } from 'vitest';
import type { BacktestCandle } from '../types/backtest.types';
import {
  aggregateRevealedCandles,
  appendRevealedCandle,
  getBacktestIntervalError,
  isValidBacktestInterval,
} from './backtestCandles';

const minute = 60_000;

function candle(
  time_ms: number,
  open: number,
  high: number,
  low: number,
  close: number,
  volume?: number
): BacktestCandle {
  return { time_ms, open, high, low, close, volume };
}

describe('aggregateRevealedCandles', () => {
  it('uses UTC start-inclusive, end-exclusive interval buckets', () => {
    const result = aggregateRevealedCandles(
      [
        candle(0, 10, 11, 9, 10.5, 2),
        candle(4 * minute, 10.5, 12, 10, 11, 3),
        candle(5 * minute, 11, 13, 10.5, 12, 4),
      ],
      5,
      2
    );

    expect(result).toEqual([
      {
        ts: 0,
        open: 10,
        high: 12,
        low: 9,
        close: 11,
        volume: 5,
      },
      {
        ts: 5 * minute,
        open: 11,
        high: 13,
        low: 10.5,
        close: 12,
        volume: 4,
      },
    ]);
  });

  it('keeps gaps empty instead of synthesizing interval bars', () => {
    const result = aggregateRevealedCandles(
      [
        candle(0, 10, 11, 9, 10.5),
        candle(10 * minute, 12, 13, 11, 12.5),
      ],
      5,
      1
    );

    expect(result.map((bar) => bar.ts)).toEqual([0, 10 * minute]);
  });

  it('updates the active bar from each forward source candle', () => {
    const first = appendRevealedCandle(
      [],
      candle(0, 10, 11, 9, 10.5, 2),
      5
    );
    const second = appendRevealedCandle(
      first,
      candle(minute, 10.5, 12, 10, 11.5, 3),
      5
    );

    expect(first).toEqual([
      { ts: 0, open: 10, high: 11, low: 9, close: 10.5, volume: 2 },
    ]);
    expect(second).toEqual([
      { ts: 0, open: 10, high: 12, low: 9, close: 11.5, volume: 5 },
    ]);
  });

  it('rebuilds only through the selected available-candle cursor', () => {
    const source = [
      candle(0, 10, 11, 9, 10.5, 2),
      candle(minute, 10.5, 12, 10, 11.5, 3),
      candle(2 * minute, 11.5, 99, 1, 98, 10_000),
    ];

    const result = aggregateRevealedCandles(source, 5, 1);

    expect(result).toEqual([
      {
        ts: 0,
        open: 10,
        high: 12,
        low: 9,
        close: 11.5,
        volume: 5,
      },
    ]);
    expect(result[0]).not.toMatchObject({ high: 99, low: 1, close: 98 });
  });

  it('leaves volume undefined when no source volume is available', () => {
    const result = aggregateRevealedCandles(
      [candle(0, 10, 11, 9, 10.5), candle(minute, 10.5, 12, 10, 11)],
      5,
      1
    );

    expect(result[0]).not.toHaveProperty('volume');
  });
});

describe('custom chart interval validation', () => {
  it('accepts whole-minute intervals from 1 through 1440', () => {
    expect(isValidBacktestInterval(1)).toBe(true);
    expect(isValidBacktestInterval('1440')).toBe(true);
  });

  it('rejects empty, fractional, and out-of-range intervals', () => {
    expect(getBacktestIntervalError('')).toContain('whole-minute');
    expect(isValidBacktestInterval('1.5')).toBe(false);
    expect(isValidBacktestInterval(0)).toBe(false);
    expect(isValidBacktestInterval(1_441)).toBe(false);
  });
});
