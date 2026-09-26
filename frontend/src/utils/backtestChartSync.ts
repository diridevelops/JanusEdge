export interface UtcTimeRange {
  from: number;
  to: number;
}

export interface LogicalTimeRange {
  from: number;
  to: number;
}

const MILLISECONDS_PER_MINUTE = 60_000;
const MAX_INTERVAL_MINUTES = 1_440;

function getIntervalMilliseconds(intervalMinutes: number): number {
  if (
    !Number.isInteger(intervalMinutes)
    || intervalMinutes < 1
    || intervalMinutes > MAX_INTERVAL_MINUTES
  ) {
    throw new RangeError('Chart interval must be a whole number from 1 to 1440 minutes.');
  }
  return intervalMinutes * MILLISECONDS_PER_MINUTE;
}

/** Find the latest timestamp <= timeMs in a sorted ascending timestamp list. */
export function findNearestPriorCandleIndex(
  sortedCandleTimes: readonly number[],
  timeMs: number
): number | null {
  if (!Number.isFinite(timeMs)) {
    throw new RangeError('Crosshair time must be a finite UTC timestamp.');
  }

  let low = 0;
  let high = sortedCandleTimes.length;
  while (low < high) {
    const middle = low + Math.floor((high - low) / 2);
    const candidate = sortedCandleTimes[middle];
    if (candidate !== undefined && candidate <= timeMs) low = middle + 1;
    else high = middle;
  }

  return low === 0 ? null : low - 1;
}

export function findNearestPriorCandleTime(
  sortedCandleTimes: readonly number[],
  timeMs: number
): number | null {
  const index = findNearestPriorCandleIndex(sortedCandleTimes, timeMs);
  return index === null ? null : sortedCandleTimes[index] ?? null;
}

/** Find the first timestamp >= timeMs in a sorted ascending timestamp list. */
export function findFirstCandleIndexAtOrAfter(
  sortedCandleTimes: readonly number[],
  timeMs: number
): number | null {
  if (!Number.isFinite(timeMs)) {
    throw new RangeError('Seek time must be a finite UTC timestamp.');
  }

  let low = 0;
  let high = sortedCandleTimes.length;
  while (low < high) {
    const middle = low + Math.floor((high - low) / 2);
    const candidate = sortedCandleTimes[middle];
    if (candidate !== undefined && candidate < timeMs) low = middle + 1;
    else high = middle;
  }
  return low < sortedCandleTimes.length ? low : null;
}

export function findFirstCandleTimeAtOrAfter(
  sortedCandleTimes: readonly number[],
  timeMs: number
): number | null {
  const index = findFirstCandleIndexAtOrAfter(sortedCandleTimes, timeMs);
  return index === null ? null : sortedCandleTimes[index] ?? null;
}

/** Round absolute UTC bounds outward to the target chart's bucket boundaries. */
export function roundUtcRangeOutward(
  range: UtcTimeRange,
  intervalMinutes: number
): UtcTimeRange {
  const intervalMs = getIntervalMilliseconds(intervalMinutes);
  if (
    !Number.isFinite(range.from)
    || !Number.isFinite(range.to)
    || range.from > range.to
  ) {
    throw new RangeError('UTC range must contain finite, ordered bounds.');
  }

  return {
    from: Math.floor(range.from / intervalMs) * intervalMs,
    to: Math.ceil(range.to / intervalMs) * intervalMs,
  };
}

/** Map CandleKit/Lightweight Charts logical bounds to enclosing UTC bar times. */
export function logicalRangeToUtcRange(
  sortedCandleTimes: readonly number[],
  range: LogicalTimeRange
): UtcTimeRange | null {
  if (
    sortedCandleTimes.length === 0
    || !Number.isFinite(range.from)
    || !Number.isFinite(range.to)
    || range.from > range.to
  ) return null;

  const fromIndex = Math.max(0, Math.min(sortedCandleTimes.length - 1, Math.floor(range.from)));
  const toIndex = Math.max(0, Math.min(sortedCandleTimes.length - 1, Math.floor(range.to)));
  const from = sortedCandleTimes[fromIndex];
  const to = sortedCandleTimes[toIndex];
  return from === undefined || to === undefined ? null : { from, to };
}

/** Map rounded UTC bounds outward to logical indexes in a target chart. */
export function utcRangeToLogicalRange(
  sortedCandleTimes: readonly number[],
  range: UtcTimeRange
): LogicalTimeRange | null {
  if (
    sortedCandleTimes.length === 0
    || !Number.isFinite(range.from)
    || !Number.isFinite(range.to)
    || range.from > range.to
    || range.to < sortedCandleTimes[0]!
    || range.from > sortedCandleTimes[sortedCandleTimes.length - 1]!
  ) return null;

  const fromIndex = findNearestPriorCandleIndex(sortedCandleTimes, range.from) ?? 0;
  const nextIndex = findFirstCandleIndexAtOrAfter(sortedCandleTimes, range.to);
  const toIndex = nextIndex ?? sortedCandleTimes.length - 1;
  return { from: fromIndex, to: Math.max(fromIndex, toIndex) };
}
