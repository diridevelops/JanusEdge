import type {
  BacktestRandomPeriodMonths,
  CreateBacktestRunRequest,
} from '../types/backtest.types';

interface BacktestRunRequestValues {
  instrument: string;
  startDate: string;
  endDate: string;
  periodSelection: 'manual' | 'random';
  periodMonths: BacktestRandomPeriodMonths;
  blindMode?: boolean;
  initialBalanceUsd: number;
  riskPercent: number;
  totalSpreadPips: number;
  slippagePips: number;
  commissionUsdPerLotPerSide: number;
}

/** Preserve the manual request shape and omit dates for random selection. */
export function buildCreateBacktestRunRequest(
  values: BacktestRunRequestValues,
  displayTimezone: string
): CreateBacktestRunRequest {
  if (values.blindMode || values.periodSelection === 'random') {
    return {
      instrument: values.instrument,
      display_timezone: displayTimezone,
      period_selection: 'random',
      period_months: values.periodMonths,
      initial_balance_usd: values.initialBalanceUsd,
      risk_percent: values.riskPercent,
      execution_costs: {
        total_spread_pips: values.totalSpreadPips,
        slippage_pips: values.slippagePips,
        commission_usd_per_lot_per_side: values.commissionUsdPerLotPerSide,
      },
      ...(values.blindMode ? { blind_mode: true as const } : {}),
    };
  }
  return {
    instrument: values.instrument,
    start_date: values.startDate,
    end_date: values.endDate,
    display_timezone: displayTimezone,
    initial_balance_usd: values.initialBalanceUsd,
    risk_percent: values.riskPercent,
    execution_costs: {
      total_spread_pips: values.totalSpreadPips,
      slippage_pips: values.slippagePips,
      commission_usd_per_lot_per_side: values.commissionUsdPerLotPerSide,
    },
  };
}
