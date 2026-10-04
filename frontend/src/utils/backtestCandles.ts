import type { BacktestCandle } from '../types/backtest.types';

/** A candle aggregated from only the source candles revealed so far. */
export interface BacktestAggregatedBar {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

const MIN_INTERVAL_MINUTES = 1;
const MAX_INTERVAL_MINUTES = 1_440;
const MILLISECONDS_PER_MINUTE = 60_000;

/** Return the validation message for a custom interval, or null when valid. */
export function getBacktestIntervalError(value: string | number): string | null {
  const minutes = typeof value === 'number' ? value : Number(value);
  if (!Number.isInteger(minutes) || minutes < 1 || minutes > 1_440) {
    return 'Enter a whole-minute interval from 1 to 1440.';
  }
  return null;
}

export function isValidBacktestInterval(value: string | number): boolean {
  return getBacktestIntervalError(value) === null;
}

function getIntervalMilliseconds(intervalMinutes: number): number {
  if (
    !Number.isInteger(intervalMinutes)
    || intervalMinutes < MIN_INTERVAL_MINUTES
    || intervalMinutes > MAX_INTERVAL_MINUTES
  ) {
    throw new RangeError('Chart interval must be a whole number from 1 to 1440 minutes.');
  }

  return intervalMinutes * MILLISECONDS_PER_MINUTE;
}

function bucketStart(timeMs: number, intervalMs: number): number {
  return Math.floor(timeMs / intervalMs) * intervalMs;
}

function hasVolume(
  candle: BacktestCandle
): candle is BacktestCandle & { volume: number } {
  return typeof candle.volume === 'number' && Number.isFinite(candle.volume);
}

function createBar(
  candle: BacktestCandle,
  intervalMs: number
): BacktestAggregatedBar {
  const bar: BacktestAggregatedBar = {
    ts: bucketStart(candle.time_ms, intervalMs),
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  };

  if (hasVolume(candle)) {
    bar.volume = candle.volume;
  }
  return bar;
}

function addToBar(
  bar: BacktestAggregatedBar,
  candle: BacktestCandle
): BacktestAggregatedBar {
  const updated: BacktestAggregatedBar = {
    ...bar,
    high: Math.max(bar.high, candle.high),
    low: Math.min(bar.low, candle.low),
    close: candle.close,
  };

  if (hasVolume(candle)) {
    updated.volume = (bar.volume ?? 0) + candle.volume;
  }
  return updated;
}

/**
 * Return UTC-aligned bars for the revealed source prefix ending at cursorIndex.
 * A cursor index of -1 represents the state before the first source candle.
 */
export function aggregateRevealedCandles(
  candles: readonly BacktestCandle[],
  intervalMinutes: number,
  cursorIndex: number
): BacktestAggregatedBar[] {
  const intervalMs = getIntervalMilliseconds(intervalMinutes);
  if (!Number.isInteger(cursorIndex) || cursorIndex < -1) {
    throw new RangeError('Replay cursor index must be an integer of -1 or greater.');
  }
  if (cursorIndex < 0 || candles.length === 0) {
    return [];
  }

  const lastIndex = Math.min(cursorIndex, candles.length - 1);
  const bars: BacktestAggregatedBar[] = [];
  let previousTime = Number.NEGATIVE_INFINITY;

  for (let index = 0; index <= lastIndex; index += 1) {
    const candle = candles[index];
    if (!candle || !Number.isFinite(candle.time_ms) || candle.time_ms <= previousTime) {
      throw new RangeError('Source candles must have strictly increasing UTC timestamps.');
    }
    previousTime = candle.time_ms;

    const nextBar = createBar(candle, intervalMs);
    const lastBar = bars[bars.length - 1];
    if (lastBar?.ts === nextBar.ts) {
      bars[bars.length - 1] = addToBar(lastBar, candle);
    } else {
      bars.push(nextBar);
    }
  }

  return bars;
}

/**
 * Incrementally incorporate one forward source candle into the current bars.
 * Seeking or stepping backward should rebuild with aggregateRevealedCandles.
 */
export function appendRevealedCandle(
  bars: readonly BacktestAggregatedBar[],
  candle: BacktestCandle,
  intervalMinutes: number
): BacktestAggregatedBar[] {
  const intervalMs = getIntervalMilliseconds(intervalMinutes);
  if (!Number.isFinite(candle.time_ms)) {
    throw new RangeError('Source candle timestamp must be a finite UTC value.');
  }

  const nextBar = createBar(candle, intervalMs);
  const lastBar = bars[bars.length - 1];
  if (!lastBar) {
    return [nextBar];
  }
  if (nextBar.ts < lastBar.ts) {
    throw new RangeError('Forward replay candles must not move to an earlier interval.');
  }
  if (nextBar.ts === lastBar.ts) {
    return [...bars.slice(0, -1), addToBar(lastBar, candle)];
  }
  return [...bars, nextBar];
}
