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
      ...(values.blindMode ? { blind_mode: true as const } : {}),
    };
  }
  return {
    instrument: values.instrument,
    start_date: values.startDate,
    end_date: values.endDate,
    display_timezone: displayTimezone,
  };
}
