import type { BacktestCandle } from '../types/backtest.types';

/** lightweight-charts price formatting for the Backtest instrument catalog. */
export interface BacktestPriceFormat {
  type: 'price';
  precision: number;
  minMove: number;
}

const DEFAULT_PRICE_FORMAT: BacktestPriceFormat = {
  type: 'price',
  precision: 2,
  minMove: 0.01,
};

const FIAT_CURRENCY_CODES = new Set([
  'AUD', 'CAD', 'CHF', 'CNH', 'CNY', 'CZK', 'DKK', 'EUR', 'GBP', 'HKD', 'HUF',
  'IDR', 'ILS', 'INR', 'JPY', 'KRW', 'MXN', 'NOK', 'NZD', 'PHP', 'PLN', 'RON',
  'RUB', 'SAR', 'SEK', 'SGD', 'THB', 'TRY', 'TWD', 'USD', 'ZAR',
]);

/**
 * Dukascopy FX symbols use five fractional digits, or three when quoted in JPY.
 * Other catalog instruments retain the normal two-decimal price display.
 */
export function getBacktestPriceFormat(instrument: string): BacktestPriceFormat {
  const match = instrument.trim().toUpperCase().match(/^([A-Z]{3})[./_-]?([A-Z]{3})$/);
  const baseCurrency = match?.[1];
  const quoteCurrency = match?.[2];
  if (
    !baseCurrency
    || !quoteCurrency
    || !FIAT_CURRENCY_CODES.has(baseCurrency)
    || !FIAT_CURRENCY_CODES.has(quoteCurrency)
  ) {
    return DEFAULT_PRICE_FORMAT;
  }

  const precision = quoteCurrency === 'JPY' ? 3 : 5;
  return {
    type: 'price',
    precision,
    minMove: 10 ** -precision,
  };
}

/** Return the smallest display precision that preserves a Blind run's raw tick. */
export function getBacktestDisplayPricePrecision(
  instrument: string,
  blindMode: boolean,
  referencePrice: number | null | undefined
): number {
  const rawPrecision = getBacktestPriceFormat(instrument).precision;
  if (!blindMode || !Number.isFinite(referencePrice) || referencePrice === 0) {
    return rawPrecision;
  }
  const displayedTick = (10 ** -rawPrecision) * Math.abs(100 / Number(referencePrice));
  if (!Number.isFinite(displayedTick) || displayedTick <= 0) return rawPrecision;
  return Math.min(12, Math.max(rawPrecision, Math.ceil(-Math.log10(displayedTick) - 1e-12)));
}

/** Convert a canonical price to the stable display scale used by Blind runs. */
export function normalizeBacktestPrice(
  price: number,
  referencePrice: number
): number {
  if (!Number.isFinite(price)) {
    throw new RangeError('Blind chart prices must be finite.');
  }
  if (!Number.isFinite(referencePrice) || referencePrice === 0) {
    throw new RangeError('Blind chart reference price must be finite and non-zero.');
  }
  return 100 * price / referencePrice;
}

/** Normalize OHLC while retaining a valid high/low range for negative refs. */
export function normalizeBacktestCandle(
  candle: BacktestCandle,
  referencePrice: number
): BacktestCandle {
  const open = normalizeBacktestPrice(candle.open, referencePrice);
  const close = normalizeBacktestPrice(candle.close, referencePrice);
  const transformedHigh = normalizeBacktestPrice(candle.high, referencePrice);
  const transformedLow = normalizeBacktestPrice(candle.low, referencePrice);
  return {
    ...candle,
    open,
    high: Math.max(transformedHigh, transformedLow),
    low: Math.min(transformedHigh, transformedLow),
    close,
  };
}
