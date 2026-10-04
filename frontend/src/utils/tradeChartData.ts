import { getOHLC } from '../api/marketData.api';
import { getBacktestChartCandles } from '../api/backtests.api';
import type { ChartInterval, OHLCDataPoint } from '../types/marketData.types';
import type { Trade } from '../types/trade.types';

/** Load backtest trades from their frozen run snapshot and other trades as before. */
export async function getTradeChartCandles(
  trade: Pick<Trade, 'backtest_run_id' | 'symbol' | 'raw_symbol'>,
  interval: Exclude<ChartInterval, '1d'>,
  start: string,
  end: string,
  forceRefresh: boolean
): Promise<OHLCDataPoint[]> {
  if (trade.backtest_run_id) {
    const candles = await getBacktestChartCandles(trade.backtest_run_id, {
      start,
      end,
      interval,
    });
    return candles.map((candle) => ({
      time: Math.floor(candle.time_ms / 1000),
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
      volume: candle.volume,
    }));
  }

  return getOHLC({
    symbol: trade.symbol,
    raw_symbol: trade.raw_symbol,
    interval,
    start,
    end,
    force_refresh: forceRefresh,
  });
}
