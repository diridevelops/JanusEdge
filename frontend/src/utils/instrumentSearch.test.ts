import { describe, expect, it } from 'vitest';
import {
  filterInstrumentSearch,
  matchesInstrumentSearch,
  normalizeInstrumentSearch,
} from './instrumentSearch';

describe('instrument search', () => {
  it('normalizes case and separators', () => {
    expect(normalizeInstrumentSearch(' eur USD / ')).toBe('EURUSD');
    expect(matchesInstrumentSearch(['EUR-USD'], 'eur usd')).toBe(true);
    expect(matchesInstrumentSearch(['AAPL.US-USD'], 'AAPL')).toBe(true);
  });

  it('requires a contiguous, correctly ordered match after normalization', () => {
    expect(matchesInstrumentSearch(['EUR-USD'], 'EUEUSD')).toBe(false);
    expect(matchesInstrumentSearch(['EUR-USD'], 'USDEUR')).toBe(false);
  });

  it('matches any supplied field and preserves item order', () => {
    const rows = [
      { pair: 'BTC/USD', base: 'BTC', quote: 'USD' },
      { pair: 'EUR/USD', base: 'EUR', quote: 'USD' },
      { pair: 'AAPL.US-USD', base: 'AAPL.US', quote: 'USD' },
    ];

    expect(filterInstrumentSearch(rows, 'aapl us', (row) => [
      row.pair,
      row.base,
      row.quote,
    ])).toEqual([rows[2]]);
    expect(filterInstrumentSearch(rows, 'usd', (row) => [row.quote])).toEqual(rows);
    expect(filterInstrumentSearch(rows, '---', (row) => [row.pair])).toEqual(rows);
  });
});
