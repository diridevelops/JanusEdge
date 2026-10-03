import { describe, expect, it } from 'vitest';
import type { SymbolMappings } from '../types/auth.types';
import { resolveManualTradeInstrument } from './manualTradeInstrument';

const eurUsdSettings = {
  base_currency: 'EUR',
  quote_currency: 'USD',
  pip_size: 0.0001,
  tick_size: 0.00001,
  price_precision: 5,
  contract_size: 100_000,
  min_lots: 0.01,
  lot_increment: 0.01,
  supported_for_simulation: true,
};

describe('resolveManualTradeInstrument', () => {
  it.each(['EUR/USD', 'eur-usd', 'EUR-USD'])(
    'resolves %s to the canonical Settings row',
    (symbol) => {
      const mappings: SymbolMappings = {
        instruments: { 'EUR-USD': eurUsdSettings },
        forex: {
          'EUR/USD': {
            ...eurUsdSettings,
            price_precision: 4,
          },
        },
      };

      const result = resolveManualTradeInstrument(symbol, mappings);

      expect(result?.canonicalSymbol).toBe('EUR-USD');
      expect(result?.source).toBe('settings');
      expect(result?.mapping.price_precision).toBe(5);
      expect(result?.supported).toBe(true);
    },
  );

  it('preserves dots in asset symbols while accepting slash aliases', () => {
    const mappings: SymbolMappings = {
      instruments: {
        'AAPL.US-USD': {
          base_currency: 'AAPL.US',
          quote_currency: 'USD',
          pip_size: 0.01,
          tick_size: 0.25,
          price_precision: 2,
          contract_size: 1,
          min_lots: 1,
          lot_increment: 1,
          supported_for_simulation: true,
        },
      },
    };

    expect(
      resolveManualTradeInstrument('aapl.us/usd', mappings)?.canonicalSymbol,
    ).toBe('AAPL.US-USD');
    expect(resolveManualTradeInstrument('AAPLUSD', mappings)).toBeNull();
  });

  it('falls back to legacy Forex mappings only when Settings has no match', () => {
    const mappings: SymbolMappings = {
      forex: {
        'USD/JPY': {
          base_currency: 'USD',
          quote_currency: 'JPY',
          pip_size: 0.01,
          price_precision: 3,
          contract_size: 100_000,
        },
      },
    };

    const result = resolveManualTradeInstrument('USD-JPY', mappings);

    expect(result?.canonicalSymbol).toBe('USD/JPY');
    expect(result?.source).toBe('legacy_forex');
    expect(result?.supported).toBe(true);
  });

  it('marks incomplete or explicitly unsupported Settings rows unusable', () => {
    const mappings: SymbolMappings = {
      instruments: {
        'BAD.US-USD': {
          base_currency: 'BAD.US',
          quote_currency: 'USD',
          supported_for_simulation: false,
        },
      },
    };

    expect(resolveManualTradeInstrument('BAD.US-USD', mappings)?.supported)
      .toBe(false);
  });
});
