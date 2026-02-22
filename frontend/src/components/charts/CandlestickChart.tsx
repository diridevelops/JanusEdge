import { createChart, type IChartApi, type IPriceLine, type ISeriesApi } from 'lightweight-charts';
import { useCallback, useEffect, useRef } from 'react';
import type { Execution } from '../../types/execution.types';
import type { ChartInterval, OHLCDataPoint } from '../../types/marketData.types';

const CHART_INTERVALS: ChartInterval[] = ['1m', '5m', '15m'];

/** Map chart interval to duration in seconds. */
const INTERVAL_SECONDS: Record<ChartInterval, number> = {
  '1m': 60,
  '5m': 300,
  '15m': 900,
  '1h': 3600,
  '1d': 86400,
};

interface CandlestickChartProps {
  /** OHLC data from backend market data API. */
  ohlcData: OHLCDataPoint[];
  /** Trade executions to render as markers. */
  executions: Execution[];
  /** Current chart interval. */
  interval: ChartInterval;
  /** Callback when user changes interval. */
  onIntervalChange: (interval: ChartInterval) => void;
  /** Average entry price line. */
  avgEntryPrice?: number;
  /** Average exit price line. */
  avgExitPrice?: number;
  /** Whether data is loading. */
  isLoading?: boolean;
  /** Display timezone (IANA) for shifting chart times. */
  displayTimezone?: string;
}

/**
 * Compute the UTC offset in seconds for a given IANA
 * timezone at a specific UTC epoch timestamp.
 */
function getTimezoneOffsetSeconds(
  tz: string,
  epochSeconds: number
): number {
  const d = new Date(epochSeconds * 1000);
  // Format the datetime parts in the target timezone
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(d);

  const get = (type: string) =>
    parseInt(parts.find((p) => p.type === type)?.value ?? '0', 10);

  const utcMs = d.getTime();
  // Reconstruct the target-timezone wall time as if it were UTC
  const targetWallUtcMs = Date.UTC(
    get('year'),
    get('month') - 1,
    get('day'),
    get('hour') === 24 ? 0 : get('hour'),
    get('minute'),
    get('second')
  );
  return Math.round((targetWallUtcMs - utcMs) / 1000);
}

/** TradingView Lightweight Charts wrapper for candlestick display. */
export function CandlestickChart({
  ohlcData,
  executions,
  interval,
  onIntervalChange,
  avgEntryPrice,
  avgExitPrice,
  isLoading,
  displayTimezone,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  /** Shift a UTC epoch timestamp to display timezone. */
  const shiftTime = useCallback(
    (utcEpoch: number): number => {
      if (!displayTimezone) return utcEpoch;
      return utcEpoch + getTimezoneOffsetSeconds(displayTimezone, utcEpoch);
    },
    [displayTimezone]
  );

  const buildMarkers = useCallback(() => {
    if (!executions.length) return [];

    const intervalSec = INTERVAL_SECONDS[interval];

    return executions
      .map((exec) => {
        const utcEpoch = Math.floor(new Date(exec.timestamp).getTime() / 1000);
        // Floor to the start of the bar interval so
        // markers align with the correct candlestick
        const floored = Math.floor(utcEpoch / intervalSec) * intervalSec;
        return {
          time: shiftTime(floored) as unknown as import('lightweight-charts').Time,
          position: (exec.side === 'Buy' ? 'belowBar' : 'aboveBar') as 'belowBar' | 'aboveBar',
          color: exec.side === 'Buy' ? '#22c55e' : '#ef4444',
          shape: (exec.side === 'Buy' ? 'arrowUp' : 'arrowDown') as 'arrowUp' | 'arrowDown',
          text: `${exec.side} ${exec.quantity} @ ${exec.price.toFixed(2)}`,
        };
      })
      .sort((a, b) => (a.time as number) - (b.time as number));
  }, [executions, shiftTime, interval]);

  // Create / destroy chart
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#ffffff' },
        textColor: '#374151',
      },
      grid: {
        vertLines: { color: '#f3f4f6' },
        horzLines: { color: '#f3f4f6' },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: '#e5e7eb',
      },
      timeScale: {
        borderColor: '#e5e7eb',
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: 400,
    });

    const series = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#16a34a',
      borderDownColor: '#dc2626',
      wickUpColor: '#16a34a',
      wickDownColor: '#dc2626',
      priceLineVisible: false,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    // Resize observer
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Update data when ohlcData changes
  useEffect(() => {
    if (!seriesRef.current || !ohlcData.length) return;

    const data = ohlcData.map((d) => ({
      time: shiftTime(d.time) as unknown as import('lightweight-charts').Time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    seriesRef.current.setData(data);

    // Set markers
    const markers = buildMarkers();
    if (markers.length > 0) {
      seriesRef.current.setMarkers(markers);
    }

    // Remove previous price lines
    for (const line of priceLinesRef.current) {
      seriesRef.current.removePriceLine(line);
    }
    priceLinesRef.current = [];

    // Add price lines
    if (avgEntryPrice) {
      const line = seriesRef.current.createPriceLine({
        price: avgEntryPrice,
        color: '#22c55e',
        lineWidth: 1,
        lineStyle: 2, // Dashed
        axisLabelVisible: true,
        title: 'Avg Entry',
      });
      priceLinesRef.current.push(line);
    }

    if (avgExitPrice) {
      const line = seriesRef.current.createPriceLine({
        price: avgExitPrice,
        color: '#ef4444',
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'Avg Exit',
      });
      priceLinesRef.current.push(line);
    }

    // Fit content
    chartRef.current?.timeScale().fitContent();
  }, [ohlcData, buildMarkers, avgEntryPrice, avgExitPrice, shiftTime]);

  return (
    <div className="space-y-2">
      {/* Interval selector */}
      <div className="flex items-center gap-1">
        {CHART_INTERVALS.map((iv) => (
          <button
            key={iv}
            onClick={() => onIntervalChange(iv)}
            className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
              interval === iv
                ? 'bg-brand-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {iv}
          </button>
        ))}
      </div>

      {/* Chart container */}
      <div className="relative border border-gray-200 rounded-lg overflow-hidden">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/70 z-10">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
          </div>
        )}
        {!ohlcData.length && !isLoading && (
          <div className="absolute inset-0 flex items-center justify-center text-gray-400 text-sm">
            No chart data available
          </div>
        )}
        <div ref={containerRef} />
      </div>
    </div>
  );
}
