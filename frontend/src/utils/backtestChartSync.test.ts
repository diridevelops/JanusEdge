import { describe, expect, it } from 'vitest';
import {
  findFirstCandleTimeAtOrAfter,
  findNearestPriorCandleTime,
  logicalRangeToUtcRange,
  roundUtcRangeOutward,
  utcRangeToLogicalRange,
} from './backtestChartSync';

const minute = 60_000;

describe('findNearestPriorCandleTime', () => {
  it('snaps to the nearest available candle at or before the UTC time', () => {
    expect(
      findNearestPriorCandleTime([0, minute, 5 * minute], 3 * minute)
    ).toBe(minute);
    expect(
      findNearestPriorCandleTime([0, minute, 5 * minute], 5 * minute)
    ).toBe(5 * minute);
  });

  it('returns null when the target has no candle at or before the time', () => {
    expect(
      findNearestPriorCandleTime([minute, 2 * minute], minute - 1)
    ).toBeNull();
  });
});

describe('findFirstCandleTimeAtOrAfter', () => {
  it('snaps a seek in a gap forward to the next available candle', () => {
    expect(findFirstCandleTimeAtOrAfter([0, minute, 5 * minute], 3 * minute))
      .toBe(5 * minute);
  });

  it('returns null beyond the final available candle for completion handling', () => {
    expect(findFirstCandleTimeAtOrAfter([0, minute], 2 * minute)).toBeNull();
  });
});

describe('roundUtcRangeOutward', () => {
  it('rounds UTC pan and zoom bounds outward to target interval edges', () => {
    expect(
      roundUtcRangeOutward(
        { from: minute + 1, to: 6 * minute - 1 },
        5
      )
    ).toEqual({ from: 0, to: 10 * minute });
  });

  it('leaves already aligned bounds unchanged', () => {
    expect(
      roundUtcRangeOutward(
        { from: 5 * minute, to: 15 * minute },
        5
      )
    ).toEqual({ from: 5 * minute, to: 15 * minute });
  });
});

describe('logical and UTC chart range mapping', () => {
  it('maps a logical source range to enclosing UTC bars, including gaps', () => {
    expect(logicalRangeToUtcRange(
      [0, minute, 5 * minute, 6 * minute],
      { from: 1.2, to: 2.1 }
    )).toEqual({ from: minute, to: 5 * minute });
  });

  it('maps UTC bounds outward to target logical indexes at another interval', () => {
    expect(utcRangeToLogicalRange(
      [0, 5 * minute, 10 * minute, 15 * minute],
      { from: 2 * minute, to: 14 * minute }
    )).toEqual({ from: 0, to: 3 });
  });

  it('returns no target range when UTC bounds do not overlap available bars', () => {
    expect(utcRangeToLogicalRange(
      [5 * minute, 10 * minute],
      { from: 0, to: 4 * minute }
    )).toBeNull();
  });
});
