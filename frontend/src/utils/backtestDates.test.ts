import { describe, expect, it } from 'vitest';
import {
  getLatestAllowedBacktestEndDate,
  isValidBacktestDateRange,
} from './backtestDates';

describe('backtest date range validation', () => {
  it('allows an inclusive range through the day before the one-year anniversary', () => {
    expect(getLatestAllowedBacktestEndDate('2024-01-01')).toBe('2024-12-31');
    expect(isValidBacktestDateRange('2024-01-01', '2024-12-31')).toBe(true);
    expect(isValidBacktestDateRange('2024-01-01', '2025-01-01')).toBe(false);
  });

  it('allows February 28 after a February 29 start and rejects March 1', () => {
    expect(getLatestAllowedBacktestEndDate('2024-02-29')).toBe('2025-02-28');
    expect(isValidBacktestDateRange('2024-02-29', '2025-02-28')).toBe(true);
    expect(isValidBacktestDateRange('2024-02-29', '2025-03-01')).toBe(false);
  });

  it('rejects reversed, malformed, and impossible calendar dates', () => {
    expect(isValidBacktestDateRange('2024-03-02', '2024-03-01')).toBe(false);
    expect(isValidBacktestDateRange('2024-02-30', '2024-03-01')).toBe(false);
    expect(isValidBacktestDateRange('2024-01-01', 'not-a-date')).toBe(false);
    expect(getLatestAllowedBacktestEndDate('2023-02-29')).toBeNull();
  });
});
