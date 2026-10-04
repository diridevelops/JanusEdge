import { TickMarkType } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { createBacktestTimeFormatters } from './backtestTimeFormat';

const utcAtRomeSpringForwardBefore = Date.parse('2026-03-29T00:30:00Z') / 1_000;
const utcAtRomeSpringForwardAfter = Date.parse('2026-03-29T01:30:00Z') / 1_000;

describe('Backtest chart time formatting', () => {
  it('formats blind axis day ticks as weekday names without a calendar date', () => {
    const { tickMarkFormatter } = createBacktestTimeFormatters('Europe/Rome', true);

    expect(tickMarkFormatter(
      utcAtRomeSpringForwardBefore,
      TickMarkType.DayOfMonth,
      'en-US'
    )).toBe('Sunday');
  });

  it('formats blind cursor and crosshair timestamps as local weekday and time across DST', () => {
    const { timeFormatter } = createBacktestTimeFormatters('Europe/Rome', true);
    const before = timeFormatter(utcAtRomeSpringForwardBefore);
    const after = timeFormatter(utcAtRomeSpringForwardAfter);

    expect(before).toContain('Sunday');
    expect(after).toContain('Sunday');
    expect(before).toMatch(/01:30/);
    expect(after).toMatch(/03:30/);
    for (const label of [before, after]) {
      expect(label).not.toMatch(/2026|Mar|29/);
    }
  });

  it('retains full date formatting for non-blind runs', () => {
    const { timeFormatter, tickMarkFormatter } = createBacktestTimeFormatters('Europe/Rome');

    expect(timeFormatter(utcAtRomeSpringForwardBefore)).toMatch(/2026|Mar|29/);
    expect(tickMarkFormatter(
      utcAtRomeSpringForwardBefore,
      TickMarkType.DayOfMonth,
      'en-US'
    )).toContain('Mar');
  });
});
