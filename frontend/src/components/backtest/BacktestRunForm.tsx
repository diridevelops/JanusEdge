import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { createBacktestRun, getBacktestInstruments } from '../../api/backtests.api';
import type { BacktestRunSummary } from '../../types/backtest.types';
import {
  getBacktestDateRangeError,
  getLatestAllowedBacktestEndDate,
} from '../../utils/backtestDates';

export interface BacktestRunFormValues {
  instrument: string;
  startDate: string;
  endDate: string;
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
  const rangeError = startDate && endDate
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
    const validationError = getBacktestDateRangeError(startDate, endDate);
    if (validationError) {
      setFormError(validationError);
      return;
    }

    setIsSubmitting(true);
    try {
      const run = await createBacktestRun({
        instrument,
        start_date: startDate,
        end_date: endDate,
        display_timezone: displayTimezone,
      });
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
        <select
          id="backtest-instrument"
          required
          value={instrument}
          onChange={(event) => {
            setInstrument(event.target.value);
            setFormError(null);
          }}
          disabled={isLoadingInstruments || !instruments.length || isSubmitting}
          className="input-field"
        >
          <option value="" disabled>Select an instrument</option>
          {instruments.map((code) => <option key={code} value={code}>{code}</option>)}
        </select>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="backtest-start-date" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Start date
          </label>
          <input
            id="backtest-start-date"
            type="date"
            required
            value={startDate}
            onChange={(event) => {
              setStartDate(event.target.value);
              setFormError(null);
            }}
            disabled={isSubmitting}
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
            required
            min={startDate || undefined}
            max={latestAllowedEndDate ?? undefined}
            value={endDate}
            onChange={(event) => {
              setEndDate(event.target.value);
              setFormError(null);
            }}
            disabled={isSubmitting}
            aria-invalid={Boolean(rangeError)}
            aria-describedby={rangeError ? 'backtest-date-range-error' : 'backtest-date-range-help'}
            className="input-field"
          />
        </div>
      </div>

      {rangeError ? (
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
