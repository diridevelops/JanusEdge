import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getBacktestChartCandles } from '../api/backtests.api';
import { getOHLC } from '../api/marketData.api';
import { getTradeChartCandles } from './tradeChartData';

vi.mock('../api/backtests.api', () => ({
  getBacktestChartCandles: vi.fn(),
}));

vi.mock('../api/marketData.api', () => ({
  getOHLC: vi.fn(),
}));

describe('getTradeChartCandles', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uses and converts the linked immutable run candles for backtest trades', async () => {
    vi.mocked(getBacktestChartCandles).mockResolvedValue([
      {
        time_ms: 1_767_571_200_000,
        open: 1.1,
        high: 1.2,
        low: 1.0,
        close: 1.15,
        volume: 60,
      },
    ]);

    const candles = await getTradeChartCandles(
      {
        backtest_run_id: 'run-1',
        symbol: 'EUR-USD',
        raw_symbol: 'EUR-USD',
      },
      '5m',
      '2026-01-05T00:00:00.000Z',
      '2026-01-06T00:00:00.000Z',
      true
    );

    expect(getBacktestChartCandles).toHaveBeenCalledWith('run-1', {
      start: '2026-01-05T00:00:00.000Z',
      end: '2026-01-06T00:00:00.000Z',
      interval: '5m',
    });
    expect(getOHLC).not.toHaveBeenCalled();
    expect(candles).toEqual([
      {
        time: 1_767_571_200,
        open: 1.1,
        high: 1.2,
        low: 1.0,
        close: 1.15,
        volume: 60,
      },
    ]);
  });

  it('keeps the existing imported-data path for non-backtest trades', async () => {
    const imported = [{ time: 1_767_571_200, open: 1, high: 2, low: 1, close: 2 }];
    vi.mocked(getOHLC).mockResolvedValue(imported);

    const candles = await getTradeChartCandles(
      { backtest_run_id: null, symbol: 'ES', raw_symbol: 'ES 03-26' },
      '1m',
      '2026-01-05T00:00:00.000Z',
      '2026-01-06T00:00:00.000Z',
      true
    );

    expect(getBacktestChartCandles).not.toHaveBeenCalled();
    expect(getOHLC).toHaveBeenCalledWith({
      symbol: 'ES',
      raw_symbol: 'ES 03-26',
      interval: '1m',
      start: '2026-01-05T00:00:00.000Z',
      end: '2026-01-06T00:00:00.000Z',
      force_refresh: true,
    });
    expect(candles).toBe(imported);
  });
});
