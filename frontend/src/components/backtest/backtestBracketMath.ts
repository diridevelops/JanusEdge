export type BacktestEntryType = 'market' | 'limit';
export type BacktestTradeDirection = 'long' | 'short';

export interface BacktestBracketPrices {
  entryPrice: number | null;
  stopLossPrice: number | null;
  takeProfitPrice: number | null;
}

export interface BacktestEntryInstrument {
  pipSize: number;
  pricePrecision: number;
  contractSize: number;
  quoteCurrency: string;
  /** USD per one quote-currency unit, selected as of the revealed candle close. */
  quoteToUsdRate: number | null;
}

export interface BacktestEntryCosts {
  totalSpreadPips: number;
  slippagePips: number;
  commissionUsdPerLotPerSide: number;
}

export interface BacktestRiskAccount {
  currentBalanceUsd: number;
  riskPercent: number;
}

export interface BacktestBracketSizingInput extends BacktestBracketPrices {
  entryType: BacktestEntryType;
  direction: BacktestTradeDirection;
  instrument: BacktestEntryInstrument;
  account: BacktestRiskAccount;
  costs?: BacktestEntryCosts;
  autoSize: boolean;
  manualLots: number | null;
}

export interface BacktestBracketSizing {
  riskBudgetUsd: number | null;
  usdPipValuePerStandardLot: number | null;
  stopDistancePips: number | null;
  targetDistancePips: number | null;
  quantityLots: number | null;
  projectedRiskUsd: number | null;
  projectedRiskPercent: number | null;
  projectedRewardUsd: number | null;
  riskRewardRatio: number | null;
  canPlaceOrder: boolean;
  errors: string[];
}

export interface BacktestEntryOrderDraft extends BacktestBracketPrices {
  entryType: BacktestEntryType;
  direction: BacktestTradeDirection;
  quantityLots: number;
  autoSize: boolean;
  riskBudgetUsd: number;
  projectedRiskUsd: number;
}

export interface DefaultBacktestBracket extends BacktestBracketPrices {
  stopDistancePips: number | null;
  error?: string;
}

export function roundPriceToPrecision(value: number, precision: number): number {
  if (!Number.isFinite(value) || !Number.isInteger(precision) || precision < 0 || precision > 12) {
    return Number.NaN;
  }

  return Number(value.toFixed(precision));
}

export function isPriceAtPrecision(value: number | null, precision: number): value is number {
  if (value == null || !Number.isFinite(value) || !Number.isInteger(precision) || precision < 0 || precision > 12) {
    return false;
  }

  const rounded = roundPriceToPrecision(value, precision);
  const tolerance = (10 ** -precision) * 1e-7;
  return Math.abs(value - rounded) <= tolerance;
}

function getUsdPerQuoteUnit(instrument: BacktestEntryInstrument): number | null {
  if (instrument.quoteCurrency.trim().toUpperCase() === 'USD') return 1;
  return Number.isFinite(instrument.quoteToUsdRate) && (instrument.quoteToUsdRate ?? 0) > 0
    ? instrument.quoteToUsdRate
    : null;
}

function isCorrectlyPositioned(
  direction: BacktestTradeDirection,
  prices: BacktestBracketPrices
): boolean {
  const { entryPrice, stopLossPrice, takeProfitPrice } = prices;
  if (entryPrice == null || stopLossPrice == null || takeProfitPrice == null) return false;
  if (![entryPrice, stopLossPrice, takeProfitPrice].every(Number.isFinite)) return false;

  return direction === 'long'
    ? stopLossPrice < entryPrice && takeProfitPrice > entryPrice
    : stopLossPrice > entryPrice && takeProfitPrice < entryPrice;
}

export function createDefaultBacktestBracket(input: {
  entryPrice: number;
  direction: BacktestTradeDirection;
  instrument: BacktestEntryInstrument;
  account: BacktestRiskAccount;
}): DefaultBacktestBracket {
  const { direction, instrument, account } = input;
  if (!Number.isFinite(input.entryPrice)) {
    return { entryPrice: null, stopLossPrice: null, takeProfitPrice: null, stopDistancePips: null, error: 'A finite entry price is required.' };
  }

  const precision = instrument.pricePrecision;
  if (!Number.isInteger(precision) || precision < 0 || precision > 12) {
    return { entryPrice: input.entryPrice, stopLossPrice: null, takeProfitPrice: null, stopDistancePips: null, error: 'Instrument price precision is invalid.' };
  }
  const entryPrice = roundPriceToPrecision(input.entryPrice, precision);
  const rate = getUsdPerQuoteUnit(instrument);
  const budget = account.currentBalanceUsd * account.riskPercent / 100;
  const accountValid = Number.isFinite(account.currentBalanceUsd) && account.currentBalanceUsd > 0
    && Number.isFinite(account.riskPercent) && account.riskPercent > 0 && account.riskPercent <= 100;
  if (!(instrument.pipSize > 0) || !(instrument.contractSize > 0) || !rate || !accountValid || !Number.isFinite(budget) || budget <= 0) {
    return {
      entryPrice,
      stopLossPrice: null,
      takeProfitPrice: null,
      stopDistancePips: null,
      error: rate ? 'Instrument and risk settings must be positive and finite.' : 'A completed quote-to-USD rate is required for this instrument.',
    };
  }

  const pipValue = instrument.pipSize * instrument.contractSize * rate;
  const minimumTick = 10 ** -precision;
  const rawStopOffset = budget / (instrument.contractSize * rate);
  if (!Number.isFinite(pipValue) || !Number.isFinite(rawStopOffset) || rawStopOffset <= 0) {
    return { entryPrice, stopLossPrice: null, takeProfitPrice: null, stopDistancePips: null, error: 'Could not calculate a finite initial stop distance.' };
  }
  const stopOffset = Math.max(minimumTick, Number(rawStopOffset.toFixed(precision)));
  const stopDistancePips = stopOffset / instrument.pipSize;
  const sideOffset = direction === 'long' ? 1 : -1;
  const stopSign = -sideOffset;
  const stopLossPrice = roundPriceToPrecision(entryPrice + stopSign * stopOffset, precision);
  const takeProfitPrice = roundPriceToPrecision(entryPrice + sideOffset * stopOffset, precision);

  if (!(pipValue > 0) || !Number.isFinite(stopLossPrice) || !Number.isFinite(takeProfitPrice) || stopOffset <= 0) {
    return { entryPrice, stopLossPrice: null, takeProfitPrice: null, stopDistancePips: null, error: 'Could not calculate a precision-valid initial bracket.' };
  }

  return { entryPrice, stopLossPrice, takeProfitPrice, stopDistancePips };
}

export function calculateBacktestBracketSizing(input: BacktestBracketSizingInput): BacktestBracketSizing {
  const { entryPrice, stopLossPrice, takeProfitPrice, direction, instrument, account, autoSize, manualLots } = input;
  const costs = input.costs ?? { totalSpreadPips: 0, slippagePips: 0, commissionUsdPerLotPerSide: 0 };
  const errors: string[] = [];
  const riskBudgetUsd = Number.isFinite(account.currentBalanceUsd) && account.currentBalanceUsd > 0
    && Number.isFinite(account.riskPercent) && account.riskPercent > 0 && account.riskPercent <= 100
    ? account.currentBalanceUsd * account.riskPercent / 100
    : null;
  if (riskBudgetUsd == null) errors.push('Balance and risk percentage must be finite and positive; risk percentage cannot exceed 100%.');

  const precisionValid = Number.isInteger(instrument.pricePrecision)
    && instrument.pricePrecision >= 0 && instrument.pricePrecision <= 12;
  const instrumentValid = precisionValid && Number.isFinite(instrument.pipSize) && instrument.pipSize > 0
    && Number.isFinite(instrument.contractSize) && instrument.contractSize > 0;
  if (!instrumentValid) errors.push('Instrument pip size, contract size, or price precision is invalid.');

  const quoteRate = getUsdPerQuoteUnit(instrument);
  if (quoteRate == null) errors.push('A completed quote-to-USD rate is required for this instrument.');

  const usdPipValuePerStandardLot = instrumentValid && quoteRate != null
    ? instrument.pipSize * instrument.contractSize * quoteRate
    : null;
  const priceValues = [entryPrice, stopLossPrice, takeProfitPrice];
  const allPricesAtPrecision = precisionValid && priceValues.every((price) => isPriceAtPrecision(price, instrument.pricePrecision));
  if (!allPricesAtPrecision) errors.push('Entry, stop, and target must be finite and use the instrument price precision.');
  const correctSides = isCorrectlyPositioned(direction, { entryPrice, stopLossPrice, takeProfitPrice });
  if (!correctSides) errors.push(direction === 'long'
    ? 'For a long entry, the stop must be below entry and the target above entry.'
    : 'For a short entry, the stop must be above entry and the target below entry.');

  const costsValid = [costs.totalSpreadPips, costs.slippagePips, costs.commissionUsdPerLotPerSide]
    .every((value) => Number.isFinite(value) && value >= 0);
  if (!costsValid) errors.push('Spread, slippage, and commission must be finite and nonnegative.');

  const stopDistancePips = entryPrice != null && stopLossPrice != null && instrument.pipSize > 0
    ? Math.abs(entryPrice - stopLossPrice) / instrument.pipSize
    : null;
  const targetDistancePips = entryPrice != null && takeProfitPrice != null && instrument.pipSize > 0
    ? Math.abs(takeProfitPrice - entryPrice) / instrument.pipSize
    : null;
  const costsPerLotUsd = usdPipValuePerStandardLot != null && costsValid
    ? (costs.totalSpreadPips + 2 * costs.slippagePips) * usdPipValuePerStandardLot
      + 2 * costs.commissionUsdPerLotPerSide
    : null;
  const riskPerLotUsd = stopDistancePips != null && costsPerLotUsd != null && usdPipValuePerStandardLot != null
    ? stopDistancePips * usdPipValuePerStandardLot + costsPerLotUsd
    : null;
  const rewardPerLotUsd = targetDistancePips != null && costsPerLotUsd != null && usdPipValuePerStandardLot != null
    ? targetDistancePips * usdPipValuePerStandardLot - costsPerLotUsd
    : null;

  let quantityLots: number | null = null;
  if (autoSize) {
    if (riskBudgetUsd != null && riskPerLotUsd != null && riskPerLotUsd > 0) {
      quantityLots = Math.floor((riskBudgetUsd / riskPerLotUsd) * 1000) / 1000;
      if (quantityLots < 0.001) {
        quantityLots = null;
        errors.push('The minimum size of 0.001 lots would exceed the USD risk budget.');
      }
    }
  } else if (manualLots != null && Number.isFinite(manualLots) && manualLots >= 0.001
    && Math.abs(manualLots * 1000 - Math.round(manualLots * 1000)) < 1e-6) {
    quantityLots = manualLots;
  } else {
    errors.push('Enter manual size in 0.001-lot increments (minimum 0.001 lots).');
  }

  const projectedRiskUsd = quantityLots != null && riskPerLotUsd != null ? quantityLots * riskPerLotUsd : null;
  const projectedRiskPercent = projectedRiskUsd != null && riskBudgetUsd != null && riskBudgetUsd > 0
    ? projectedRiskUsd / riskBudgetUsd * 100
    : null;
  const projectedRewardUsd = quantityLots != null && rewardPerLotUsd != null ? quantityLots * rewardPerLotUsd : null;
  const riskRewardRatio = projectedRiskUsd != null && projectedRiskUsd > 0 && projectedRewardUsd != null
    ? projectedRewardUsd / projectedRiskUsd
    : null;
  const pricesValid = allPricesAtPrecision && correctSides;
  const sizingValid = quantityLots != null && Number.isFinite(quantityLots);
  const calculationValid = riskBudgetUsd != null && instrumentValid && quoteRate != null && costsValid;

  return {
    riskBudgetUsd,
    usdPipValuePerStandardLot,
    stopDistancePips,
    targetDistancePips,
    quantityLots,
    projectedRiskUsd,
    projectedRiskPercent,
    projectedRewardUsd,
    riskRewardRatio,
    canPlaceOrder: pricesValid && sizingValid && calculationValid,
    errors,
  };
}

export function createBacktestEntryOrderDraft(
  input: BacktestBracketSizingInput,
  sizing: BacktestBracketSizing
): BacktestEntryOrderDraft | null {
  if (!sizing.canPlaceOrder || sizing.quantityLots == null || sizing.riskBudgetUsd == null || sizing.projectedRiskUsd == null
    || input.entryPrice == null || input.stopLossPrice == null || input.takeProfitPrice == null) {
    return null;
  }

  return {
    entryType: input.entryType,
    direction: input.direction,
    entryPrice: input.entryPrice,
    stopLossPrice: input.stopLossPrice,
    takeProfitPrice: input.takeProfitPrice,
    quantityLots: sizing.quantityLots,
    autoSize: input.autoSize,
    riskBudgetUsd: sizing.riskBudgetUsd,
    projectedRiskUsd: sizing.projectedRiskUsd,
  };
}
