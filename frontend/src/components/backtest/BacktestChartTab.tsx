import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { ChartViewApi } from '@getcandlekit/charts/react';
import type { BacktestChartTab as BacktestChartTabConfig } from '../../types/backtest.types';
import { getBacktestIntervalError } from '../../utils/backtestCandles';
import { CandleKitReplayChart } from './CandleKitReplayChart';

interface BacktestChartTabProps {
  runId: string;
  instrument: string;
  tab: BacktestChartTabConfig;
  displayTimezone: string;
  blindMode: boolean;
  normalizedReferencePrice: number | null;
  cursorTimeMs: number;
  registerDrawingFlusher: (
    tabId: string,
    flush: () => Promise<void> | void
  ) => () => void;
  onIntervalChange: (tabId: string, intervalMinutes: number) => void;
  onChartReady: (
    tabId: string,
    api: ChartViewApi,
    onFollowStateChange: (isFollowing: boolean) => void
  ) => void | (() => void);
  snapToLive: (tabId: string) => void;
}

const TIMEFRAME_PRESETS = [
  { minutes: 1, label: '1m' },
  { minutes: 5, label: '5m' },
  { minutes: 15, label: '15m' },
  { minutes: 30, label: '30m' },
  { minutes: 60, label: '1h' },
  { minutes: 240, label: '4h' },
  { minutes: 1_440, label: '1d' },
] as const;

function isPresetInterval(minutes: number): boolean {
  return TIMEFRAME_PRESETS.some((preset) => preset.minutes === minutes);
}

/** A persisted chart panel with controlled, whole-minute interval validation. */
export function BacktestChartTab({
  runId,
  instrument,
  tab,
  displayTimezone,
  blindMode,
  normalizedReferencePrice,
  cursorTimeMs,
  registerDrawingFlusher,
  onIntervalChange,
  onChartReady,
  snapToLive,
}: BacktestChartTabProps) {
  const [customIntervalDraft, setCustomIntervalDraft] = useState(String(tab.interval_minutes));
  const [intervalError, setIntervalError] = useState<string | null>(null);
  const [customDialogOpen, setCustomDialogOpen] = useState(false);
  const customDialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    setCustomIntervalDraft(String(tab.interval_minutes));
    setIntervalError(null);
  }, [tab.interval_minutes]);

  useEffect(() => {
    const dialog = customDialogRef.current;
    if (!dialog) return;
    if (customDialogOpen && !dialog.open) dialog.showModal();
    if (!customDialogOpen && dialog.open) dialog.close();
  }, [customDialogOpen]);

  function selectTimeframe(value: string) {
    if (value === 'custom') {
      setCustomIntervalDraft(String(tab.interval_minutes));
      setIntervalError(null);
      setCustomDialogOpen(true);
      return;
    }

    const intervalMinutes = Number(value);
    if (intervalMinutes !== tab.interval_minutes) {
      onIntervalChange(tab.id, intervalMinutes);
    }
  }

  function applyCustomInterval(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = getBacktestIntervalError(customIntervalDraft);
    setIntervalError(validationError);
    if (validationError) return;
    const intervalMinutes = Number(customIntervalDraft);
    if (intervalMinutes !== tab.interval_minutes) {
      onIntervalChange(tab.id, intervalMinutes);
    }
    setCustomDialogOpen(false);
  }

  return (
    <section className="backtest-chart-tab flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-white dark:bg-gray-900">
      <div className="relative min-h-0 flex-1 p-1">
        <CandleKitReplayChart
          key={`${tab.id}:${tab.interval_minutes}`}
          tabId={tab.id}
          runId={runId}
          intervalMinutes={tab.interval_minutes}
          displayTimezone={displayTimezone}
          blindMode={blindMode}
          normalizedReferencePrice={normalizedReferencePrice}
          cursorTimeMs={cursorTimeMs}
          registerDrawingFlusher={registerDrawingFlusher}
          onChartReady={onChartReady}
          snapToLive={snapToLive}
        />
        <div className="backtest-chart-controls">
          <span className="backtest-instrument-label" aria-label={`Instrument ${instrument}`}>
            {instrument}
          </span>
          <label htmlFor={`backtest-timeframe-${tab.id}`} className="sr-only">
            Chart timeframe
          </label>
          <div className="backtest-timeframe-control relative">
            <select
              id={`backtest-timeframe-${tab.id}`}
              aria-label="Chart timeframe"
              value={String(tab.interval_minutes)}
              onChange={(event) => selectTimeframe(event.target.value)}
              className="backtest-timeframe-select"
            >
              {TIMEFRAME_PRESETS.map((preset) => (
                <option key={preset.minutes} value={preset.minutes}>
                  {preset.label}
                </option>
              ))}
              {!isPresetInterval(tab.interval_minutes) && (
                <option value={tab.interval_minutes}>{tab.interval_minutes}m</option>
              )}
              <option value="custom">Custom</option>
            </select>
          </div>
        </div>
        <span className="sr-only">
          Chart volume represents quoted liquidity from bid and ask, not executed trade volume.
        </span>
        <dialog
          ref={customDialogRef}
          aria-labelledby={`backtest-custom-timeframe-title-${tab.id}`}
          className="backtest-timeframe-dialog fixed m-auto w-[calc(100%-2rem)] max-w-xs rounded-lg border border-gray-300 bg-white p-4 text-gray-900 shadow-xl backdrop:bg-black/40 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
          onCancel={(event) => {
            event.preventDefault();
            setCustomDialogOpen(false);
          }}
        >
          <form onSubmit={applyCustomInterval}>
            <h2
              id={`backtest-custom-timeframe-title-${tab.id}`}
              className="text-sm font-semibold"
            >
              Custom timeframe
            </h2>
            <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
              Enter a whole number of minutes from 1 to 1,440.
            </p>
            <label
              htmlFor={`backtest-custom-timeframe-${tab.id}`}
              className="mt-3 block text-xs font-medium"
            >
              Minutes
            </label>
            <input
              id={`backtest-custom-timeframe-${tab.id}`}
              type="number"
              inputMode="numeric"
              min={1}
              max={1_440}
              step={1}
              value={customIntervalDraft}
              aria-invalid={Boolean(intervalError)}
              aria-describedby={intervalError ? `backtest-interval-error-${tab.id}` : undefined}
              onChange={(event) => {
                setCustomIntervalDraft(event.target.value);
                setIntervalError(null);
              }}
              className="mt-1 w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
            />
            {intervalError && (
              <p
                id={`backtest-interval-error-${tab.id}`}
                className="mt-1 text-xs text-red-600 dark:text-red-400"
                role="alert"
              >
                {intervalError}
              </p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCustomDialogOpen(false)}
                className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
              >
                Apply
              </button>
            </div>
          </form>
        </dialog>
      </div>
    </section>
  );
}
