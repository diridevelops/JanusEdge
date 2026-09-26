import { useEffect, useState } from 'react';
import type { ChartViewApi } from '@getcandlekit/charts/react';
import type { BacktestChartTab as BacktestChartTabConfig } from '../../types/backtest.types';
import { getBacktestIntervalError } from '../../utils/backtestCandles';
import { CandleKitReplayChart } from './CandleKitReplayChart';

interface BacktestChartTabProps {
  runId: string;
  tab: BacktestChartTabConfig;
  totalTabs: number;
  cursorTimeMs: number;
  registerDrawingFlusher: (
    tabId: string,
    flush: () => Promise<void> | void
  ) => () => void;
  onIntervalChange: (tabId: string, intervalMinutes: number) => void;
  onRemove: (tabId: string) => void;
  onChartReady: (tabId: string, api: ChartViewApi) => void;
  onChartDispose: (tabId: string) => void;
}

/** A persisted chart panel with controlled, whole-minute interval validation. */
export function BacktestChartTab({
  runId,
  tab,
  totalTabs,
  cursorTimeMs,
  registerDrawingFlusher,
  onIntervalChange,
  onRemove,
  onChartReady,
  onChartDispose,
}: BacktestChartTabProps) {
  const [rawInterval, setRawInterval] = useState(String(tab.interval_minutes));
  const [intervalError, setIntervalError] = useState<string | null>(null);

  useEffect(() => {
    setRawInterval(String(tab.interval_minutes));
    setIntervalError(null);
  }, [tab.interval_minutes]);

  function commitInterval() {
    const validationError = getBacktestIntervalError(rawInterval);
    setIntervalError(validationError);
    if (validationError) return;
    const intervalMinutes = Number(rawInterval);
    if (intervalMinutes !== tab.interval_minutes) {
      onIntervalChange(tab.id, intervalMinutes);
    }
  }

  return (
    <section className="backtest-chart-tab min-w-0 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-gray-700">
        <div>
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">
            Chart {tab.position + 1}
            <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
              {tab.interval_minutes}m
            </span>
          </h2>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Volume shows quoted liquidity (bid + ask), not executed trades.
          </p>
        </div>
        <div className="flex items-start gap-3">
          <div>
            <label
              htmlFor={`backtest-interval-${tab.id}`}
              className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-300"
            >
              Interval (minutes)
            </label>
            <input
              id={`backtest-interval-${tab.id}`}
              type="number"
              inputMode="numeric"
              min={1}
              max={1_440}
              step={1}
              value={rawInterval}
              aria-invalid={Boolean(intervalError)}
              aria-describedby={intervalError ? `backtest-interval-error-${tab.id}` : undefined}
              onChange={(event) => {
                setRawInterval(event.target.value);
                setIntervalError(getBacktestIntervalError(event.target.value));
              }}
              onBlur={commitInterval}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  event.currentTarget.blur();
                }
              }}
              className="w-32 rounded-md border border-gray-300 bg-white px-2.5 py-1.5 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
            />
            {intervalError && (
              <p
                id={`backtest-interval-error-${tab.id}`}
                className="mt-1 max-w-48 text-xs text-red-600 dark:text-red-400"
                role="alert"
              >
                {intervalError}
              </p>
            )}
          </div>
          <button
            type="button"
            disabled={totalTabs <= 1}
            onClick={() => onRemove(tab.id)}
            aria-label={`Remove chart ${tab.position + 1}`}
            className="mt-5 rounded-md px-2 py-1.5 text-sm text-gray-500 hover:bg-gray-100 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-40 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
          >
            Remove
          </button>
        </div>
      </header>
      <div className="h-[330px] p-2">
        <CandleKitReplayChart
          key={`${tab.id}:${tab.interval_minutes}`}
          tabId={tab.id}
          runId={runId}
          intervalMinutes={tab.interval_minutes}
          cursorTimeMs={cursorTimeMs}
          registerDrawingFlusher={registerDrawingFlusher}
          onChartReady={onChartReady}
          onChartDispose={onChartDispose}
        />
      </div>
    </section>
  );
}
