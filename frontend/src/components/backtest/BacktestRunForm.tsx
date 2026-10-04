import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  createBacktestRun,
  createManualBacktestRun,
  getBacktestInstruments,
  getManualBacktestDataset,
  getManualBacktestInstruments,
  previewManualBacktestImport,
} from '../../api/backtests.api';
import { InstrumentCombobox } from './InstrumentCombobox';
import type {
  BacktestRunSummary,
  BacktestRandomPeriodMonths,
  BacktestManualDataset,
  BacktestManualImportPreview,
  BacktestManualInstrument,
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
  sourceMode?: 'dukascopy' | 'manual';
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
      if ('error' in data && typeof data.error === 'object' && data.error !== null) {
        const appError = data.error as { message?: unknown };
        if (typeof appError.message === 'string') return appError.message;
      }
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return 'Could not create the Backtest run. Please try again.';
}

function getManualConflict(error: unknown): { dates: string[] } | null {
  if (typeof error !== 'object' || error === null || !('response' in error)) return null;
  const data = (error as { response?: { data?: unknown } }).response?.data;
  if (typeof data !== 'object' || data === null || !('error' in data)) return null;
  const appError = (data as { error?: unknown }).error;
  if (typeof appError !== 'object' || appError === null || !('details' in appError)) return null;
  const details = (appError as { details?: unknown }).details;
  if (typeof details !== 'object' || details === null) return null;
  const detailsValue = details as {
    requires_confirmation?: unknown;
    affected_dates?: unknown;
    conflicting_dates?: unknown;
  };
  const dates = Array.isArray(detailsValue.affected_dates)
    ? detailsValue.affected_dates
    : detailsValue.conflicting_dates;
  if (!detailsValue.requires_confirmation || !Array.isArray(dates)) return null;
  return { dates: dates.filter((value): value is string => typeof value === 'string') };
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
  const [sourceMode, setSourceMode] = useState<'dukascopy' | 'manual'>(
    initialValues?.sourceMode ?? 'dukascopy'
  );
  const [manualInstruments, setManualInstruments] = useState<BacktestManualInstrument[]>([]);
  const [isLoadingManualInstruments, setIsLoadingManualInstruments] = useState(false);
  const [manualDataset, setManualDataset] = useState<BacktestManualDataset | null>(null);
  const [manualPreview, setManualPreview] = useState<BacktestManualImportPreview | null>(null);
  const [manualFiles, setManualFiles] = useState<File[]>([]);
  const [manualPreviewError, setManualPreviewError] = useState<string | null>(null);
  const manualPreviewRequest = useRef(0);
  const [isPreviewingFiles, setIsPreviewingFiles] = useState(false);
  const [manualFallbackRate, setManualFallbackRate] = useState('');
  const [showMergeConfirmation, setShowMergeConfirmation] = useState(false);
  const [conflictingDates, setConflictingDates] = useState<string[]>([]);
  const [instrumentError, setInstrumentError] = useState<string | null>(null);
  const [instrument, setInstrument] = useState(
    initialValues?.sourceMode === 'manual' ? '' : initialValues?.instrument ?? ''
  );
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
        if (sourceMode !== 'dukascopy') return;
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
  }, [initialValues?.instrument, sourceMode]);

  useEffect(() => {
    if (sourceMode !== 'manual') return;
    let isCurrent = true;
    setIsLoadingManualInstruments(true);
    setInstrument('');
    setManualDataset(null);
    setManualPreview(null);
    setManualFiles([]);
    getManualBacktestInstruments()
      .then((rows) => {
        if (isCurrent) setManualInstruments(rows);
      })
      .catch((error: unknown) => {
        if (isCurrent) setFormError(getRequestErrorMessage(error));
      })
      .finally(() => {
        if (isCurrent) setIsLoadingManualInstruments(false);
      });
    return () => { isCurrent = false; };
  }, [sourceMode]);

  useEffect(() => {
    if (sourceMode !== 'manual' || !instrument) {
      setManualDataset(null);
      setManualPreview(null);
      return;
    }
    let isCurrent = true;
    setManualDataset(null);
    setManualPreview(null);
    getManualBacktestDataset(instrument)
      .then((dataset) => {
        if (!isCurrent) return;
        setManualDataset(dataset);
        if (dataset.available_dates.length) {
          const firstDate = dataset.available_dates[0] ?? '';
          const lastDate = dataset.available_dates[dataset.available_dates.length - 1] ?? '';
          setStartDate((current) => dataset.available_dates.includes(current)
            ? current : firstDate);
          setEndDate((current) => dataset.available_dates.includes(current)
            ? current : lastDate);
        }
      })
      .catch((error: unknown) => {
        if (isCurrent) setFormError(getRequestErrorMessage(error));
      });
    return () => { isCurrent = false; };
  }, [instrument, sourceMode]);

  const latestAllowedEndDate = useMemo(
    () => getLatestAllowedBacktestEndDate(startDate),
    [startDate]
  );
  const isRandomSelection = blindMode || periodSelection === 'random';
  const rangeError = !isRandomSelection && startDate && endDate
    ? getBacktestDateRangeError(startDate, endDate)
    : null;

  const manualDates = manualPreview?.available_dates
    ?? manualDataset?.available_dates
    ?? [];
  const selectedManualInstrument = manualInstruments.find(
    (item) => item.instrument === instrument
  );

  function handleManualFilesChanged(fileList: FileList | null) {
    const requestId = ++manualPreviewRequest.current;
    const selectedInstrument = instrument;
    const files = fileList ? Array.from(fileList) : [];
    setManualFiles(files);
    setManualPreview(null);
    setManualPreviewError(null);
    setShowMergeConfirmation(false);
    setFormError(null);
    if (!selectedInstrument || files.length === 0) {
      setIsPreviewingFiles(false);
      return;
    }
    setIsPreviewingFiles(true);
    void previewManualBacktestImport(selectedInstrument, files)
      .then((preview) => {
        if (requestId !== manualPreviewRequest.current) return;
        setManualPreview(preview);
        if (preview.available_dates.length) {
          const firstDate = preview.available_dates[0] ?? '';
          const lastDate = preview.available_dates[preview.available_dates.length - 1] ?? '';
          setStartDate((current) => preview.available_dates.includes(current)
            ? current : firstDate);
          setEndDate((current) => preview.available_dates.includes(current)
            ? current : lastDate);
        }
      })
      .catch((error: unknown) => {
        if (requestId === manualPreviewRequest.current) {
          setManualPreviewError(getRequestErrorMessage(error));
        }
      })
      .finally(() => {
        if (requestId === manualPreviewRequest.current) setIsPreviewingFiles(false);
      });
  }

  async function submitRun(confirmMerge: boolean) {
    setFormError(null);

    if (!instrument) {
      setFormError(sourceMode === 'manual'
        ? 'Select an instrument from Settings.'
        : 'Select a supported instrument.');
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

    if (sourceMode === 'manual') {
      if (isPreviewingFiles) {
        setFormError('Wait for the CSV import preview to finish.');
        return;
      }
      if (manualFiles.length && !manualPreview) {
        setFormError(manualPreviewError ?? 'The selected CSV files could not be read. Choose the files again and retry.');
        return;
      }
      if (!manualDates.length || (!manualFiles.length && !manualDataset?.revision)) {
        setFormError(manualPreviewError ?? 'Select HistData CSV files or use an existing manual import.');
        return;
      }
      if (!isRandomSelection && (!manualDates.includes(startDate) || !manualDates.includes(endDate))) {
        setFormError('Choose start and end dates present in the imported data.');
        return;
      }
      if (manualPreview?.requires_confirmation && !confirmMerge) {
        setConflictingDates(manualPreview.overlap_dates);
        setShowMergeConfirmation(true);
        return;
      }
      if (selectedManualInstrument?.quote_currency !== 'USD') {
        const fallback = manualFallbackRate.trim() ? Number(manualFallbackRate) : undefined;
        if (manualFallbackRate.trim() && (!Number.isFinite(fallback) || Number(fallback) <= 0)) {
          setFormError('The quote-to-USD fallback rate must be a positive finite number.');
          return;
        }
        if (!selectedManualInstrument?.conversion_supported && fallback == null) {
          setFormError('Enter a quote-to-USD fallback rate because no historical conversion route is configured.');
          return;
        }
      }
    }

    setIsSubmitting(true);
    try {
      const values = {
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
      };
      const run = sourceMode === 'manual'
        ? await createManualBacktestRun({
          instrument,
          display_timezone: displayTimezone,
          ...(isRandomSelection ? {} : { start_date: startDate, end_date: endDate }),
          period_selection: isRandomSelection ? 'random' : 'manual',
          ...(isRandomSelection ? { period_months: periodMonths } : {}),
          warmup_days: parsedWarmupDays,
          blind_mode: blindMode,
          initial_balance_usd: parsedInitialBalance,
          risk_percent: parsedRiskPercent,
          execution_costs: {
            total_spread_pips: parsedExecutionCosts[0]!,
            slippage_pips: parsedExecutionCosts[1]!,
            commission_usd_per_lot_per_side: parsedExecutionCosts[2]!,
          },
          expected_dataset_revision: manualPreview?.expected_revision
            ?? manualDataset?.revision
            ?? null,
          confirm_overwrite: confirmMerge,
          ...(manualFallbackRate.trim()
            ? { quote_to_usd_fallback_rate: Number(manualFallbackRate) }
            : {}),
        }, manualFiles)
        : await createBacktestRun(
          buildCreateBacktestRunRequest(values, displayTimezone)
        );
      setShowMergeConfirmation(false);
      await onCreated(run);
    } catch (error) {
      const conflict = sourceMode === 'manual' ? getManualConflict(error) : null;
      if (conflict) {
        setConflictingDates(conflict.dates);
        setShowMergeConfirmation(true);
        return;
      }
      setFormError(getRequestErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitRun(false);
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

      <div role="group" aria-label="Candle data source" className="inline-flex rounded-lg border border-gray-300 p-1 dark:border-gray-700">
        {(['dukascopy', 'manual'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            aria-pressed={sourceMode === mode}
            onClick={() => {
              setSourceMode(mode);
              setInstrument('');
              setFormError(null);
              setShowMergeConfirmation(false);
            }}
            disabled={isSubmitting}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${sourceMode === mode
              ? 'bg-blue-600 text-white'
              : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'}`}
          >
            {mode === 'dukascopy' ? 'Dukascopy' : 'Manual import'}
          </button>
        ))}
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
          instruments={sourceMode === 'manual'
            ? manualInstruments.map((item) => item.instrument)
            : instruments}
          disabled={sourceMode === 'manual'
            ? isLoadingManualInstruments || !manualInstruments.length || isSubmitting
            : isLoadingInstruments || !instruments.length || isSubmitting}
          placeholder={sourceMode === 'manual'
            ? isLoadingManualInstruments ? 'Loading Settings instruments…' : 'Select a Settings instrument'
            : isLoadingInstruments ? 'Loading instruments…' : 'Select an instrument'}
          onChange={(selectedInstrument) => {
            manualPreviewRequest.current += 1;
            setIsPreviewingFiles(false);
            setInstrument(selectedInstrument);
            setManualFiles([]);
            setManualDataset(null);
            setManualPreview(null);
            setManualPreviewError(null);
            setManualFallbackRate('');
            setFormError(null);
          }}
        />
      </div>

      {sourceMode === 'manual' && instrument && (
        <div className="space-y-4 rounded-lg border border-gray-200 p-4 dark:border-gray-700">
          <div>
            <label htmlFor="backtest-manual-files" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              HistData CSV files
            </label>
            <input
              key={instrument}
              id="backtest-manual-files"
              type="file"
              accept=".csv,text/csv"
              multiple
              onChange={(event) => handleManualFilesChanged(event.currentTarget.files)}
              disabled={isSubmitting || isPreviewingFiles}
              className="input-field"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Headerless one-minute bid data. Files must contain candles for {instrument}.
            </p>
            {manualPreviewError && (
              <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
                Could not read the selected CSV files: {manualPreviewError}
              </p>
            )}
          </div>
          {manualPreview?.incoming_dates.length ? (
            <p className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-200">
              Selected files contain candles from {manualPreview.incoming_dates[0]} through {manualPreview.incoming_dates[manualPreview.incoming_dates.length - 1]} ({manualPreview.incoming_dates.length} dates).
            </p>
          ) : null}
          {(manualDataset?.available_dates.length || manualPreview?.available_dates.length) ? (
            <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-200">
              <p>
                {manualPreview?.incoming_dates.length
                  ? 'Combined cached and uploaded data covers'
                  : 'Previously imported data covers'}{' '}
                {manualDates[0]} through {manualDates[manualDates.length - 1]} ({manualDates.length} available dates).
                {manualPreview?.overlap_count
                  ? ` ${manualPreview.overlap_count} uploaded candle timestamps overlap cached data.`
                  : ''}
              </p>
              <details className="mt-1">
                <summary className="cursor-pointer font-medium">Show available dates</summary>
                <ul className="mt-1 grid max-h-28 grid-cols-2 gap-x-4 overflow-auto sm:grid-cols-4">
                  {manualDates.map((day) => <li key={day}>{day}</li>)}
                </ul>
              </details>
            </div>
          ) : manualDataset && !manualDataset.revision && !manualFiles.length ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No previous import is cached for this instrument. Choose CSV files to continue.
            </p>
          ) : null}
          {isPreviewingFiles && (
            <p className="text-sm text-gray-500 dark:text-gray-400">Checking uploaded candles against the cached import…</p>
          )}
          {selectedManualInstrument?.quote_currency !== 'USD' && selectedManualInstrument && (
            <div>
              <label htmlFor="backtest-manual-fallback-rate" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Quote-to-USD fallback rate (USD per {selectedManualInstrument.quote_currency})
              </label>
              <input
                id="backtest-manual-fallback-rate"
                type="number"
                inputMode="decimal"
                min="0"
                step="any"
                value={manualFallbackRate}
                onChange={(event) => setManualFallbackRate(event.target.value)}
                disabled={isSubmitting}
                className="input-field max-w-xs"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Historical Dukascopy conversion is used when available; this rate is only the fallback.
              </p>
            </div>
          )}
        </div>
      )}

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
          {sourceMode === 'manual' ? (
            <select
              id="backtest-start-date"
              required={!isRandomSelection}
              value={startDate}
              onChange={(event) => {
                setStartDate(event.target.value);
                if (endDate && event.target.value > endDate) setEndDate(event.target.value);
                setFormError(null);
              }}
              disabled={isSubmitting || isRandomSelection || !manualDates.length}
              className="input-field"
            >
              <option value="">Select an imported date</option>
              {manualDates.map((day) => <option key={day} value={day}>{day}</option>)}
            </select>
          ) : (
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
          )}
        </div>
        <div>
          <label htmlFor="backtest-end-date" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            End date
          </label>
          {sourceMode === 'manual' ? (
            <select
              id="backtest-end-date"
              required={!isRandomSelection}
              value={endDate}
              onChange={(event) => {
                setEndDate(event.target.value);
                setFormError(null);
              }}
              disabled={isSubmitting || isRandomSelection || !manualDates.length}
              aria-invalid={Boolean(rangeError)}
              aria-describedby={rangeError ? 'backtest-date-range-error' : 'backtest-date-range-help'}
              className="input-field"
            >
              <option value="">Select an imported date</option>
              {manualDates.filter((day) => !startDate || day >= startDate).map((day) => (
                <option key={day} value={day}>{day}</option>
              ))}
            </select>
          ) : (
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
          )}
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
          {sourceMode === 'manual'
            ? 'A random period will be selected from the imported dates. If the selected duration is longer than the imported history, all imported dates will be used.'
            : 'The worker will choose a start date with available one-minute candles. The period uses your configured display timezone.'}
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

      {showMergeConfirmation && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4">
          <div role="alertdialog" aria-modal="true" aria-labelledby="manual-merge-title" className="w-full max-w-lg rounded-xl border border-amber-300 bg-amber-50 p-5 text-sm text-amber-950 shadow-xl dark:border-amber-800 dark:bg-gray-900 dark:text-amber-100">
            <h3 id="manual-merge-title" className="font-semibold">Merge overlapping cached candles?</h3>
            <p className="mt-1">
              The files will be merged with the cached import. Identical rows will be deduplicated, and uploaded rows will replace cached candles when their values differ on these dates:
            </p>
            <ul className="mt-2 max-h-32 list-inside list-disc overflow-auto">
              {conflictingDates.map((day) => <li key={day}>{day}</li>)}
            </ul>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setShowMergeConfirmation(false)} disabled={isSubmitting} className="btn-secondary">
                Cancel
              </button>
              <button type="button" onClick={() => void submitRun(true)} disabled={isSubmitting} className="btn-primary">
                {isSubmitting ? 'Merging…' : 'Confirm merge and start run'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting
            || (sourceMode === 'manual'
              ? isLoadingManualInstruments || !manualInstruments.length || isPreviewingFiles || (!manualFiles.length && !manualDataset?.revision)
              : isLoadingInstruments || !instruments.length)
            || Boolean(rangeError)}
          className="btn-primary disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? 'Starting…' : 'Start run'}
        </button>
      </div>
    </form>
  );
}
