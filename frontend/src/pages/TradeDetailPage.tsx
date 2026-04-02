import { ArrowLeft, RefreshCw, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getOHLC } from '../api/marketData.api';
import { deleteTrade, getTrade, getTradeRunningPnL } from '../api/trades.api';
import { CandlestickChart } from '../components/charts/CandlestickChart';
import { RunningPnLChart } from '../components/charts/RunningPnLChart';
import { ExecutionList } from '../components/trade/ExecutionList';
import { StopAnalysisFields } from '../components/trade/StopAnalysisFields';
import { TagSelector } from '../components/trade/TagSelector';
import { TradeCostFields } from '../components/trade/TradeCostFields';
import { TradeMedia } from '../components/trade/TradeMedia';
import { TradeNotes } from '../components/trade/TradeNotes';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import type { Execution } from '../types/execution.types';
import type { ChartInterval, OHLCDataPoint } from '../types/marketData.types';
import type {
  RunningPnLEmptyReason,
  RunningPnLPoint,
  Trade,
} from '../types/trade.types';
import { formatCurrency, formatDateTime, formatDuration } from '../utils/formatters';
import { getTradeRMultiple } from '../utils/tradeMetrics';

const ALL_INTERVALS: ChartInterval[] = ['1m', '5m', '15m', '1h'];

/** Pick the most relevant chart interval based on trade duration. */
function bestInterval(holdingSeconds: number): ChartInterval {
  if (holdingSeconds < 20 * 60) return '1m';
  if (holdingSeconds < 60 * 60) return '5m';
  if (holdingSeconds < 4 * 60 * 60) return '15m';
  return '1h';
}

function getMarketDataFailureMessage(): string {
  return 'No stored market data was found for this trade window. Import a NinjaTrader tick-data file from Market Data to populate candles for this symbol.';
}

function getRunningPnLEmptyStateMessage(
  emptyReason: RunningPnLEmptyReason
): string | null {
  if (emptyReason === 'missing_tick_data') {
    return 'Running P&L requires stored raw tick data for this trade window. Import a NinjaTrader tick-data file from Market Data to populate it.';
  }
  if (emptyReason === 'no_ticks_in_trade_window') {
    return 'Stored raw tick data exists for this trade day, but no ticks were found between the trade entry and exit times.';
  }
  return null;
}

function SkeletonBlock({ className }: { className: string }) {
  return <div className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className}`} />;
}

function TradeDetailPageSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <SkeletonBlock className="h-5 w-5 rounded-full" />
          <div className="space-y-2">
            <SkeletonBlock className="h-8 w-40" />
            <SkeletonBlock className="h-4 w-64" />
          </div>
        </div>
        <SkeletonBlock className="h-10 w-28" />
      </div>

      <div className="card p-4">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-9">
          {Array.from({ length: 9 }).map((_, index) => (
            <div key={index} className="space-y-2">
              <SkeletonBlock className="h-3 w-16" />
              <SkeletonBlock className="h-5 w-20" />
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-6 lg:flex-row">
        <div className="card flex-1 min-w-0 p-4">
          <div className="mb-3 flex items-center justify-between">
            <SkeletonBlock className="h-4 w-24" />
            <SkeletonBlock className="h-4 w-24" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-1">
              {Array.from({ length: 4 }).map((_, index) => (
                <SkeletonBlock key={index} className="h-8 w-11 rounded-md" />
              ))}
            </div>
            <SkeletonBlock className="h-[402px] w-full rounded-lg" />
          </div>
        </div>

        <div className="card flex w-full min-h-[220px] flex-col lg:w-28">
          <div className="space-y-3 p-4">
            <SkeletonBlock className="h-4 w-12" />
            {Array.from({ length: 3 }).map((_, index) => (
              <SkeletonBlock key={index} className="h-16 w-full rounded-lg" />
            ))}
          </div>
        </div>
      </div>

      <div className="card p-4">
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="space-y-2">
              <SkeletonBlock className="h-4 w-24" />
              <SkeletonBlock className="h-10 w-full rounded-lg" />
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="card p-4">
          <SkeletonBlock className="mb-3 h-4 w-28" />
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <SkeletonBlock key={index} className="h-16 w-full rounded-lg" />
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="card p-4">
            <SkeletonBlock className="mb-3 h-4 w-20" />
            <div className="flex flex-wrap gap-2">
              {Array.from({ length: 5 }).map((_, index) => (
                <SkeletonBlock key={index} className="h-8 w-20 rounded-full" />
              ))}
            </div>
          </div>

          <div className="card p-4">
            <SkeletonBlock className="mb-3 h-4 w-24" />
            <div className="space-y-3">
              <SkeletonBlock className="h-24 w-full rounded-lg" />
              <SkeletonBlock className="h-24 w-full rounded-lg" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Trade detail page — chart, executions, notes, tags. */
export function TradeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { addToast } = useToast();
  const { user } = useAuth();

  const [trade, setTrade] = useState<Trade | null>(null);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [ohlcMap, setOhlcMap] = useState<Record<string, OHLCDataPoint[]>>({});
  const [runningPnl, setRunningPnl] = useState<RunningPnLPoint[]>([]);
  const [interval, setInterval] = useState<ChartInterval>('5m');
  const [isTradeLoading, setIsTradeLoading] = useState(true);
  const [isChartLoading, setIsChartLoading] = useState(false);
  const [isRunningPnlLoading, setIsRunningPnlLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);
  const [runningPnlError, setRunningPnlError] = useState<string | null>(null);
  const tradeRequestIdRef = useRef(0);
  const chartRequestIdRef = useRef(0);
  const runningPnlRequestIdRef = useRef(0);

  const fetchAllCharts = useCallback(
    async (
      tradeToLoad: Trade,
      options: {
        forceRefresh?: boolean;
        notifyOnMissing?: boolean;
      } = {}
    ) => {
      const requestId = chartRequestIdRef.current + 1;
      chartRequestIdRef.current = requestId;
      setIsChartLoading(true);
      setChartError(null);
      const failureMessage = getMarketDataFailureMessage();
      const { forceRefresh = false, notifyOnMissing = false } = options;

      try {
        const entryDate = new Date(tradeToLoad.entry_time);
        const exitDate = new Date(tradeToLoad.exit_time);

        const first = entryDate <= exitDate ? entryDate : exitDate;
        const last = entryDate <= exitDate ? exitDate : entryDate;

        const dayStart = new Date(
          Date.UTC(
            first.getUTCFullYear(),
            first.getUTCMonth(),
            first.getUTCDate(),
            0, 0, 0, 0
          )
        );

        const dayEnd = new Date(
          Date.UTC(
            last.getUTCFullYear(),
            last.getUTCMonth(),
            last.getUTCDate() + 1,
            0, 0, 0, 0
          )
        );

        const results = await Promise.allSettled(
          ALL_INTERVALS.map(async (iv) => {
            const data = await getOHLC({
              symbol: tradeToLoad.symbol,
              raw_symbol: tradeToLoad.raw_symbol,
              interval: iv,
              start: dayStart.toISOString(),
              end: dayEnd.toISOString(),
              force_refresh: forceRefresh,
            });

            return {
              interval: iv,
              data,
            };
          })
        );

        const map: Record<string, OHLCDataPoint[]> = {};
        let hasAnyData = false;

        for (const [index, result] of results.entries()) {
          const intervalKey = ALL_INTERVALS[index];
          if (!intervalKey) {
            continue;
          }

          if (result.status === 'fulfilled') {
            map[result.value.interval] = result.value.data;
            if (result.value.data.length > 0) {
              hasAnyData = true;
            }
            continue;
          }

          map[intervalKey] = [];
        }

        if (requestId !== chartRequestIdRef.current) {
          return null;
        }

        setOhlcMap(map);

        if (!hasAnyData) {
          setChartError(failureMessage);
          if (notifyOnMissing) {
            addToast('error', failureMessage);
          }
          return false;
        }
      } catch {
        if (requestId !== chartRequestIdRef.current) {
          return null;
        }

        setOhlcMap({});
        setChartError(failureMessage);
        if (notifyOnMissing) {
          addToast('error', failureMessage);
        }
        return false;
      } finally {
        if (requestId === chartRequestIdRef.current) {
          setIsChartLoading(false);
        }
      }

      return true;
    },
    [addToast]
  );

  const fetchRunningPnl = useCallback(async (tradeId: string) => {
    const requestId = runningPnlRequestIdRef.current + 1;
    runningPnlRequestIdRef.current = requestId;
    setIsRunningPnlLoading(true);
    setRunningPnlError(null);

    try {
      const response = await getTradeRunningPnL(tradeId);
      if (requestId !== runningPnlRequestIdRef.current) {
        return;
      }

      setRunningPnl(response.points);
      setRunningPnlError(
        getRunningPnLEmptyStateMessage(response.empty_reason)
      );
    } catch {
      if (requestId !== runningPnlRequestIdRef.current) {
        return;
      }

      setRunningPnl([]);
      setRunningPnlError('Failed to load running P&L.');
    } finally {
      if (requestId === runningPnlRequestIdRef.current) {
        setIsRunningPnlLoading(false);
      }
    }
  }, []);

  const fetchTrade = useCallback(async (preserveExisting = false) => {
    if (!id) {
      setIsTradeLoading(false);
      return;
    }

    const requestId = tradeRequestIdRef.current + 1;
    tradeRequestIdRef.current = requestId;
    chartRequestIdRef.current += 1;
    runningPnlRequestIdRef.current += 1;
    setIsTradeLoading(true);
    setIsChartLoading(false);
    setIsRunningPnlLoading(false);

    if (!preserveExisting) {
      setTrade(null);
      setExecutions([]);
      setOhlcMap({});
      setRunningPnl([]);
      setRunningPnlError(null);
    }

    try {
      const tradeData = await getTrade(id);
      if (requestId !== tradeRequestIdRef.current) {
        return;
      }

      const loadedTrade = tradeData.trade;
      const loadedExecutions = Array.isArray(tradeData.executions)
        ? tradeData.executions as Execution[]
        : [];

      setTrade(loadedTrade);
      setExecutions(loadedExecutions);
      setInterval(bestInterval(loadedTrade.holding_time_seconds));
      if (!preserveExisting) {
        setOhlcMap({});
      }
      setIsTradeLoading(false);

      void fetchAllCharts(loadedTrade);
      void fetchRunningPnl(loadedTrade.id);
    } catch {
      if (requestId !== tradeRequestIdRef.current) {
        return;
      }
      addToast('error', 'Failed to load trade');
      navigate('/trades');
      setIsTradeLoading(false);
      setIsChartLoading(false);
      setIsRunningPnlLoading(false);
    }
  }, [id, addToast, navigate, fetchAllCharts, fetchRunningPnl]);

  const handleTradeRefresh = useCallback(() => {
    void fetchTrade(true);
  }, [fetchTrade]);

  async function handleRefreshChartData() {
    if (!trade) return;
    const ok = await fetchAllCharts(trade, { forceRefresh: true });
    if (ok === true) {
      addToast('success', 'Stored candles refreshed');
    } else if (ok === false) {
      addToast('error', getMarketDataFailureMessage());
    }
  }

  useEffect(() => {
    void fetchTrade();
  }, [fetchTrade]);

  async function handleDelete() {
    if (!id || !confirm('Delete this trade permanently?')) return;
    setIsDeleting(true);
    try {
      await deleteTrade(id);
      addToast('success', 'Trade deleted');
      navigate('/trades');
    } catch {
      addToast('error', 'Failed to delete trade');
    } finally {
      setIsDeleting(false);
    }
  }

  if (isTradeLoading && !trade) {
    return <TradeDetailPageSkeleton />;
  }

  if (!trade) {
    return (
      <div className="text-center py-24 text-gray-500 dark:text-gray-400">
        <p>Trade not found.</p>
        <Link to="/trades" className="text-brand-600 hover:underline mt-2 inline-block">
          Back to Trades
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            to="/trades"
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            aria-label="Back to trades"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {trade.symbol}{' '}
              <span
                className={`text-lg ${trade.side === 'Long' ? 'text-green-600' : 'text-red-600'}`}
              >
                {trade.side}
              </span>
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {formatDateTime(trade.entry_time, user?.display_timezone)} —{' '}
              {formatDateTime(trade.exit_time, user?.display_timezone)}
            </p>
          </div>
        </div>
        <button
          onClick={handleDelete}
          disabled={isDeleting}
          className="btn-danger inline-flex items-center gap-1.5"
        >
          <Trash2 className="h-4 w-4" />
          {isDeleting ? 'Deleting...' : 'Delete'}
        </button>
      </div>

      {/* Trade summary card */}
      <div className="card p-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-9 gap-4 text-sm">
          <div>
            <p className="text-xs text-gray-500 uppercase dark:text-gray-400">Quantity</p>
            <p className="font-semibold text-gray-900 dark:text-gray-100">{trade.total_quantity}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase dark:text-gray-400">Avg Entry</p>
            <p className="font-semibold text-gray-900 dark:text-gray-100">{formatCurrency(trade.avg_entry_price)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase dark:text-gray-400">Avg Exit</p>
            <p className="font-semibold text-gray-900 dark:text-gray-100">{formatCurrency(trade.avg_exit_price)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase dark:text-gray-400">Gross P&L</p>
            <p className={`font-semibold ${trade.gross_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
              {formatCurrency(trade.gross_pnl)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase dark:text-gray-400">Fees</p>
            <p className="font-semibold text-gray-700 dark:text-gray-300">{formatCurrency(trade.fee)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase dark:text-gray-400">Net P&L</p>
            <p className={`font-bold ${trade.net_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
              {formatCurrency(trade.net_pnl)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase dark:text-gray-400">Initial Risk (No Fees)</p>
            <p className="font-semibold text-gray-900 dark:text-gray-100">
              {trade.initial_risk > 0
                ? formatCurrency(trade.initial_risk)
                : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase dark:text-gray-400">R-multiple</p>
            <p className={`font-semibold ${trade.net_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
              {(() => {
                const rMultiple = getTradeRMultiple(
                  trade.net_pnl,
                  trade.initial_risk,
                  trade.fee
                );
                return rMultiple !== null
                  ? `${rMultiple.toFixed(2)}R`
                  : '—';
              })()}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase dark:text-gray-400">Duration</p>
            <p className="font-semibold text-gray-900 dark:text-gray-100">
              {formatDuration(trade.holding_time_seconds)}
            </p>
          </div>
        </div>
      </div>

      {/* Chart + Media sidebar */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Chart */}
        <div className="card p-4 flex-1 min-w-0">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider dark:text-gray-100">
              Price Chart
            </h2>
            <button
              type="button"
              onClick={handleRefreshChartData}
              disabled={isChartLoading}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-800 disabled:opacity-50 dark:text-gray-400 dark:hover:text-gray-200"
              title="Reload stored candles for this trade day"
            >
              <RefreshCw className={`h-4 w-4 ${isChartLoading ? 'animate-spin' : ''}`} />
              Refresh Data
            </button>
          </div>
          <CandlestickChart
            ohlcData={ohlcMap[interval] ?? []}
            executions={executions}
            interval={interval}
            onIntervalChange={setInterval}
            avgEntryPrice={trade.avg_entry_price}
            avgExitPrice={trade.avg_exit_price}
            isLoading={isChartLoading}
            displayTimezone={user?.display_timezone ?? user?.timezone}
            emptyStateMessage={chartError ?? undefined}
          />
        </div>

        {/* Media sidebar — same height as chart card */}
        <div className="card w-full lg:w-28 lg:self-stretch flex flex-col min-h-0 lg:max-h-[none]">
          <div className="px-4 pt-4">
            <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider dark:text-gray-100">
              Media
            </h2>
          </div>
          <TradeMedia tradeId={trade.id} compact />
        </div>
      </div>

      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-3 dark:text-gray-100">
          Running P&amp;L
        </h2>
        <RunningPnLChart
          data={runningPnl}
          isLoading={isRunningPnlLoading}
          displayTimezone={user?.display_timezone ?? user?.timezone}
          emptyStateMessage={runningPnlError ?? undefined}
        />
      </div>

      {/* Editable detail cards */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="card p-4">
          <TradeCostFields
            tradeId={trade.id}
            trade={trade}
            onSaved={handleTradeRefresh}
          />
        </div>

        <div className="card p-4">
          <StopAnalysisFields
            tradeId={trade.id}
            trade={trade}
            onSaved={handleTradeRefresh}
          />
        </div>
      </div>

      {/* Lower section: Executions + Notes/Tags */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Executions */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-3 dark:text-gray-100">
            Executions ({executions.length})
          </h2>
          <ExecutionList executions={executions} />
        </div>

        {/* Notes and Tags */}
        <div className="space-y-6">
          <div className="card p-4">
            <TagSelector
              tradeId={trade.id}
              tagIds={trade.tag_ids}
              onChanged={handleTradeRefresh}
            />
          </div>
          <div className="card p-4">
            <TradeNotes
              tradeId={trade.id}
              preTradeNotes={trade.pre_trade_notes}
              postTradeNotes={trade.post_trade_notes}
              onSaved={handleTradeRefresh}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
