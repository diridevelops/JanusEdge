import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { createBacktestRun, getBacktestInstruments } from '../../api/backtests.api';
import { InstrumentCombobox } from './InstrumentCombobox';
import type {
  BacktestRunSummary,
  BacktestRandomPeriodMonths,
} from '../../types/backtest.types';
import {
  getBacktestDateRangeError,
  getLatestAllowedBacktestEndDate,
} from '../../utils/backtestDates';
import { buildCreateBacktestRunRequest } from '../../utils/backtestRunRequest';

export interface BacktestRunFormValues {
  instrument: string;
  startDate: string;
  endDate: string;
  periodSelection: 'manual' | 'random';
  periodMonths: BacktestRandomPeriodMonths;
  warmupDays?: number;
  blindMode: boolean;
  initialBalanceUsd: number;
  riskPercent: number;
  totalSpreadPips: number;
  slippagePips: number;
  commissionUsdPerLotPerSide: number;
}

interface BacktestRunFormProps {
  displayTimezone: string;
  initialValues?: Partial<BacktestRunFormValues>;
  onCancel: () => void;
  onCreated: (run: BacktestRunSummary) => void | Promise<void>;
}

function getRequestErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: unknown } }).response;
    const data = response?.data;
    if (typeof data === 'object' && data !== null) {
      if ('message' in data && typeof data.message === 'string') return data.message;
      if ('error' in data && typeof data.error === 'string') return data.error;
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return 'Could not create the Backtest run. Please try again.';
}

/** Select one catalog-backed instrument and an inclusive, timezone-local range. */
export function BacktestRunForm({
  displayTimezone,
  initialValues,
  onCancel,
  onCreated,
}: BacktestRunFormProps) {
  const [instruments, setInstruments] = useState<string[]>([]);
  const [isLoadingInstruments, setIsLoadingInstruments] = useState(true);
  const [instrumentError, setInstrumentError] = useState<string | null>(null);
  const [instrument, setInstrument] = useState(initialValues?.instrument ?? '');
  const [startDate, setStartDate] = useState(initialValues?.startDate ?? '');
  const [endDate, setEndDate] = useState(initialValues?.endDate ?? '');
  const [periodSelection, setPeriodSelection] = useState<'manual' | 'random'>(
    initialValues?.periodSelection ?? 'manual'
  );
  const [periodMonths, setPeriodMonths] = useState<BacktestRandomPeriodMonths>(
    initialValues?.periodMonths ?? 1
  );
  const [warmupDays, setWarmupDays] = useState(
    String(initialValues?.warmupDays ?? 0)
  );
  const [blindMode, setBlindMode] = useState(initialValues?.blindMode ?? false);
  const [initialBalanceUsd, setInitialBalanceUsd] = useState(
    String(initialValues?.initialBalanceUsd ?? 10_000)
  );
  const [riskPercent, setRiskPercent] = useState(
    String(initialValues?.riskPercent ?? 1)
  );
  const [totalSpreadPips, setTotalSpreadPips] = useState(
    String(initialValues?.totalSpreadPips ?? 0)
  );
  const [slippagePips, setSlippagePips] = useState(
    String(initialValues?.slippagePips ?? 0)
  );
  const [commissionUsdPerLotPerSide, setCommissionUsdPerLotPerSide] = useState(
    String(initialValues?.commissionUsdPerLotPerSide ?? 0)
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;
    setIsLoadingInstruments(true);
    getBacktestInstruments()
      .then((result) => {
        if (!isCurrent) return;
        const catalog = [...new Set(result)].sort((left, right) => left.localeCompare(right));
        setInstruments(catalog);
        setInstrument((current) => {
          if (current && catalog.includes(current)) return current;
          if (initialValues?.instrument && catalog.includes(initialValues.instrument)) {
            return initialValues.instrument;
          }
          return catalog[0] ?? '';
        });
        if (!catalog.length) setInstrumentError('No instruments are currently available.');
      })
      .catch(() => {
        if (isCurrent) {
          setInstrumentError('Could not load the supported instrument catalog.');
        }
      })
      .finally(() => {
        if (isCurrent) setIsLoadingInstruments(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [initialValues?.instrument]);

  const latestAllowedEndDate = useMemo(
    () => getLatestAllowedBacktestEndDate(startDate),
    [startDate]
  );
  const isRandomSelection = blindMode || periodSelection === 'random';
  const rangeError = !isRandomSelection && startDate && endDate
    ? getBacktestDateRangeError(startDate, endDate)
    : null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    if (!instrument) {
      setFormError('Select a supported instrument.');
      return;
    }
    if (!displayTimezone) {
      setFormError('Set a display timezone in Settings before creating a run.');
      return;
    }
    const parsedInitialBalance = Number(initialBalanceUsd);
    if (!Number.isFinite(parsedInitialBalance) || parsedInitialBalance <= 0) {
      setFormError('Initial balance must be a finite positive USD amount.');
      return;
    }
    const parsedRiskPercent = Number(riskPercent);
    if (
      !Number.isFinite(parsedRiskPercent)
      || parsedRiskPercent <= 0
      || parsedRiskPercent > 100
    ) {
      setFormError('Risk must be greater than 0% and no more than 100%.');
      return;
    }
    const parsedWarmupDays = warmupDays.trim() ? Number(warmupDays) : Number.NaN;
    if (!Number.isSafeInteger(parsedWarmupDays) || parsedWarmupDays < 0) {
      setFormError('Warm-up days must be a nonnegative whole number.');
      return;
    }
    const parsedExecutionCosts = [
      totalSpreadPips,
      slippagePips,
      commissionUsdPerLotPerSide,
    ].map((value) => value.trim() ? Number(value) : Number.NaN);
    if (!parsedExecutionCosts.every(
      (value) => Number.isFinite(value) && value >= 0
    )) {
      setFormError('Execution costs must be finite, nonnegative values.');
      return;
    }
    const validationError = isRandomSelection
      ? null
      : getBacktestDateRangeError(startDate, endDate);
    if (validationError) {
      setFormError(validationError);
      return;
    }

    setIsSubmitting(true);
    try {
      const run = await createBacktestRun(
        buildCreateBacktestRunRequest({
          instrument,
          startDate,
          endDate,
          periodSelection,
          periodMonths,
          warmupDays: parsedWarmupDays,
          blindMode,
          initialBalanceUsd: parsedInitialBalance,
          riskPercent: parsedRiskPercent,
          totalSpreadPips: parsedExecutionCosts[0]!,
          slippagePips: parsedExecutionCosts[1]!,
          commissionUsdPerLotPerSide: parsedExecutionCosts[2]!,
        }, displayTimezone)
      );
      await onCreated(run);
    } catch (error) {
      setFormError(getRequestErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card space-y-5 p-6" aria-labelledby="backtest-run-form-title">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="backtest-run-form-title" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            New Backtest run
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Dates use your configured display timezone: <span className="font-medium">{displayTimezone || 'not set'}</span>.
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="btn-secondary text-sm disabled:cursor-not-allowed disabled:opacity-60"
        >
          Cancel
        </button>
      </div>

      {instrumentError && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
          {instrumentError}
        </div>
      )}

      <div>
        <label htmlFor="backtest-instrument" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
          Instrument
        </label>
        <InstrumentCombobox
          id="backtest-instrument"
          value={instrument}
          instruments={instruments}
          disabled={isLoadingInstruments || !instruments.length || isSubmitting}
          placeholder={isLoadingInstruments ? 'Loading instruments…' : 'Select an instrument'}
          onChange={(selectedInstrument) => {
            setInstrument(selectedInstrument);
            setFormError(null);
          }}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="backtest-period-selection" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Period selection
          </label>
          <select
            id="backtest-period-selection"
            value={blindMode ? 'random' : periodSelection}
            onChange={(event) => {
              setPeriodSelection(event.target.value as 'manual' | 'random');
              setFormError(null);
            }}
            disabled={isSubmitting || blindMode}
            className="input-field"
          >
            <option value="manual">Choose dates</option>
            <option value="random">Random period</option>
          </select>
        </div>
        {isRandomSelection && (
          <div>
            <label htmlFor="backtest-period-months" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Random period duration
            </label>
            <select
              id="backtest-period-months"
              value={periodMonths}
              onChange={(event) => setPeriodMonths(Number(event.target.value) as BacktestRandomPeriodMonths)}
              disabled={isSubmitting}
              className="input-field"
            >
              <option value={1}>1 month</option>
              <option value={3}>3 months</option>
              <option value={6}>6 months</option>
              <option value={12}>12 months</option>
            </select>
          </div>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
        <input
          type="checkbox"
          checked={blindMode}
          onChange={(event) => {
            const enabled = event.target.checked;
            setBlindMode(enabled);
            if (enabled) setPeriodSelection('random');
            setFormError(null);
          }}
          disabled={isSubmitting}
          className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
        />
        Blind mode
      </label>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="backtest-initial-balance" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Initial balance (USD)
          </label>
          <input
            id="backtest-initial-balance"
            type="number"
            inputMode="decimal"
            step="any"
            required
            value={initialBalanceUsd}
            onChange={(event) => {
              setInitialBalanceUsd(event.target.value);
              setFormError(null);
            }}
            disabled={isSubmitting}
            className="input-field"
          />
        </div>
        <div>
          <label htmlFor="backtest-risk-percent" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Risk per entry (%)
          </label>
          <input
            id="backtest-risk-percent"
            type="number"
            inputMode="decimal"
            min="0"
            max="100"
            step="any"
            required
            value={riskPercent}
            onChange={(event) => {
              setRiskPercent(event.target.value);
              setFormError(null);
            }}
            disabled={isSubmitting}
            className="input-field"
          />
        </div>
      </div>

      <fieldset className="space-y-3 rounded-lg border border-gray-200 p-4 dark:border-gray-700">
        <legend className="px-1 text-sm font-semibold text-gray-900 dark:text-gray-100">
          Simulation execution costs
        </legend>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          These assumptions are fixed for this run and apply to simulated fills.
        </p>
        <div className="grid gap-4 sm:grid-cols-3">
          <label htmlFor="backtest-cost-spread" className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Total spread (price steps)
            <input
              id="backtest-cost-spread"
              type="number"
              min="0"
              step="any"
              required
              value={totalSpreadPips}
              onChange={(event) => {
                setTotalSpreadPips(event.currentTarget.value);
                setFormError(null);
              }}
              disabled={isSubmitting}
              className="input-field mt-1"
            />
          </label>
          <label htmlFor="backtest-cost-slippage" className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Slippage (price steps)
            <input
              id="backtest-cost-slippage"
              type="number"
              min="0"
              step="any"
              required
              value={slippagePips}
              onChange={(event) => {
                setSlippagePips(event.currentTarget.value);
                setFormError(null);
              }}
              disabled={isSubmitting}
              className="input-field mt-1"
            />
          </label>
          <label htmlFor="backtest-cost-commission" className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Commission (USD / lot / side)
            <input
              id="backtest-cost-commission"
              type="number"
              min="0"
              step="any"
              required
              value={commissionUsdPerLotPerSide}
              onChange={(event) => {
                setCommissionUsdPerLotPerSide(event.currentTarget.value);
                setFormError(null);
              }}
              disabled={isSubmitting}
              className="input-field mt-1"
            />
          </label>
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="backtest-start-date" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Start date
          </label>
          <input
            id="backtest-start-date"
            type="date"
            required={!isRandomSelection}
            value={startDate}
            onChange={(event) => {
              setStartDate(event.target.value);
              setFormError(null);
            }}
            disabled={isSubmitting || isRandomSelection}
            className="input-field"
          />
        </div>
        <div>
          <label htmlFor="backtest-end-date" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            End date
          </label>
          <input
            id="backtest-end-date"
            type="date"
            required={!isRandomSelection}
            min={startDate || undefined}
            max={latestAllowedEndDate ?? undefined}
            value={endDate}
            onChange={(event) => {
              setEndDate(event.target.value);
              setFormError(null);
            }}
            disabled={isSubmitting || isRandomSelection}
            aria-invalid={Boolean(rangeError)}
            aria-describedby={rangeError ? 'backtest-date-range-error' : 'backtest-date-range-help'}
            className="input-field"
          />
        </div>
      </div>

      <div className="max-w-xs">
        <label htmlFor="backtest-warmup-days" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
          Warm-up days
        </label>
        <input
          id="backtest-warmup-days"
          type="number"
          inputMode="numeric"
          min="0"
          step="1"
          required
          value={warmupDays}
          onChange={(event) => {
            setWarmupDays(event.target.value);
            setFormError(null);
          }}
          disabled={isSubmitting}
          className="input-field"
        />
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Calendar days before the selected period&apos;s start date, shown for context. Replay starts on start date.
        </p>
      </div>

      {isRandomSelection ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          The worker will choose a start date with available one-minute candles. The period uses your configured display timezone.
        </p>
      ) : rangeError ? (
        <p id="backtest-date-range-error" role="alert" className="text-sm text-red-600 dark:text-red-400">
          {rangeError}
        </p>
      ) : (
        <p id="backtest-date-range-help" className="text-sm text-gray-500 dark:text-gray-400">
          Choose an inclusive range shorter than one calendar year. The selected instrument uses one-minute candles.
        </p>
      )}

      {formError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">{formError}</p>
      )}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting || isLoadingInstruments || !instruments.length || Boolean(rangeError)}
          className="btn-primary disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? 'Starting…' : 'Start run'}
        </button>
      </div>
    </form>
  );
}
