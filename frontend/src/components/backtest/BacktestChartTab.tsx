import { useEffect, useState } from 'react';
import type { ChartViewApi } from '@getcandlekit/charts/react';
import type { BacktestChartTab as BacktestChartTabConfig } from '../../types/backtest.types';
import { getBacktestIntervalError } from '../../utils/backtestCandles';
import { CandleKitReplayChart } from './CandleKitReplayChart';

interface BacktestChartTabProps {
  runId: string;
  tab: BacktestChartTabConfig;
  title: string;
  displayTimezone: string;
  cursorTimeMs: number;
  registerDrawingFlusher: (
    tabId: string,
    flush: () => Promise<void> | void
  ) => () => void;
  onIntervalChange: (tabId: string, intervalMinutes: number) => void;
  onChartReady: (tabId: string, api: ChartViewApi) => void | (() => void);
}

/** A persisted chart panel with controlled, whole-minute interval validation. */
export function BacktestChartTab({
  runId,
  tab,
  title,
  displayTimezone,
  cursorTimeMs,
  registerDrawingFlusher,
  onIntervalChange,
  onChartReady,
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
    <section className="backtest-chart-tab flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-white dark:bg-gray-900">
      <header className="flex shrink-0 flex-wrap items-start justify-between gap-3 border-b border-gray-200 px-3 py-2 dark:border-gray-700">
        <div>
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">
            {title}
            <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
              {tab.interval_minutes}m
            </span>
          </h2>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Volume shows quoted liquidity (bid + ask), not executed trades.
          </p>
        </div>
        <div>
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
              className="w-28 rounded-md border border-gray-300 bg-white px-2 py-1 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
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
        </div>
      </header>
      <div className="relative min-h-0 flex-1 p-1">
        <CandleKitReplayChart
          key={`${tab.id}:${tab.interval_minutes}`}
          tabId={tab.id}
          runId={runId}
          intervalMinutes={tab.interval_minutes}
          displayTimezone={displayTimezone}
          cursorTimeMs={cursorTimeMs}
          registerDrawingFlusher={registerDrawingFlusher}
          onChartReady={onChartReady}
        />
      </div>
    </section>
  );
}
