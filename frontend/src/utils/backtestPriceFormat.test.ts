import { describe, expect, it } from 'vitest';
import type { BacktestCandle } from '../types/backtest.types';
import {
  normalizeBacktestCandle,
  normalizeBacktestPrice,
} from './backtestPriceFormat';

describe('blind Backtest price normalization', () => {
  it('normalizes a price coordinate against the fixed replay reference', () => {
    expect(normalizeBacktestPrice(1.25, 1.2)).toBeCloseTo(104.1666667);
    expect(normalizeBacktestPrice(1.2, 1.2)).toBe(100);
  });

  it('normalizes all OHLC values while retaining time and volume', () => {
    const candle: BacktestCandle = {
      time_ms: 1_774_762_200_000,
      open: 1.2,
      high: 1.24,
      low: 1.18,
      close: 1.23,
      volume: 17,
    };

    const normalized = normalizeBacktestCandle(candle, 1.2);
    expect(normalized).toMatchObject({
      time_ms: candle.time_ms,
      open: 100,
      close: 102.5,
      volume: 17,
    });
    expect(normalized.high).toBeCloseTo(103.3333333);
    expect(normalized.low).toBeCloseTo(98.3333333);
    expect(candle.open).toBe(1.2);
  });

  it('keeps open and close mapped directly for a negative reference and reorders high/low', () => {
    const candle: BacktestCandle = {
      time_ms: 0,
      open: -10,
      high: -8,
      low: -12,
      close: -9,
    };

    expect(normalizeBacktestCandle(candle, -10)).toEqual({
      ...candle,
      open: 100,
      high: 120,
      low: 80,
      close: 90,
    });
  });
});
