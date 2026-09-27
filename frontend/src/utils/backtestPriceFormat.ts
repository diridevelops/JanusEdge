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
