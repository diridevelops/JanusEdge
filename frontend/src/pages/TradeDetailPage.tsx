import { ArrowLeft, RefreshCw, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { listExecutions } from '../api/executions.api';
import { getOHLC } from '../api/marketData.api';
import { deleteTrade, getTrade } from '../api/trades.api';
import { CandlestickChart } from '../components/charts/CandlestickChart';
import { ExecutionList } from '../components/trade/ExecutionList';
import { StopAnalysisFields } from '../components/trade/StopAnalysisFields';
import { TagSelector } from '../components/trade/TagSelector';
import { TradeMedia } from '../components/trade/TradeMedia';
import { TradeNotes } from '../components/trade/TradeNotes';
import { Spinner } from '../components/ui/Spinner';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import type { Execution } from '../types/execution.types';
import type { ChartInterval, OHLCDataPoint } from '../types/marketData.types';
import type { Trade } from '../types/trade.types';
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

/** Trade detail page — chart, executions, notes, tags. */
export function TradeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { addToast } = useToast();
  const { user } = useAuth();

  const [trade, setTrade] = useState<Trade | null>(null);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [ohlcMap, setOhlcMap] = useState<Record<string, OHLCDataPoint[]>>({});
  const [interval, setInterval] = useState<ChartInterval>('5m');
  const [isLoading, setIsLoading] = useState(true);
  const [isChartLoading, setIsChartLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const chartRequestIdRef = useRef(0);

  const fetchAllCharts = useCallback(async (tradeToLoad: Trade, forceRefresh: boolean = false) => {
    const requestId = chartRequestIdRef.current + 1;
    chartRequestIdRef.current = requestId;
    setIsChartLoading(true);
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

      const results = await Promise.all(
        ALL_INTERVALS.map(async (iv) => {
          try {
            const data = await getOHLC({
              symbol: tradeToLoad.symbol,
              interval: iv,
              start: dayStart.toISOString(),
              end: dayEnd.toISOString(),
              force_refresh: forceRefresh,
            });
            return [iv, data] as const;
          } catch {
            return [iv, [] as OHLCDataPoint[]] as const;
          }
        })
      );

      const map: Record<string, OHLCDataPoint[]> = {};
      for (const [iv, data] of results) {
        map[iv] = data;
      }
      if (requestId !== chartRequestIdRef.current) {
        return null;
      }
      setOhlcMap(map);
    } catch {
      if (requestId !== chartRequestIdRef.current) {
        return null;
      }
      if (requestId === chartRequestIdRef.current) {
        setOhlcMap({});
      }
      return false;
    } finally {
      if (requestId === chartRequestIdRef.current) {
        setIsChartLoading(false);
        setIsLoading(false);
      }
    }
    return true;
  }, []);

  const fetchTrade = useCallback(async () => {
    if (!id) return;
    setIsLoading(true);
    setTrade(null);
    setExecutions([]);
    setOhlcMap({});
    try {
      const [tradeData, execData] = await Promise.all([
        getTrade(id),
        listExecutions({ trade_id: id }),
      ]);
      const loadedTrade = tradeData.trade;
      setTrade(loadedTrade);
      setExecutions(execData.executions ?? execData.items);
      setInterval(bestInterval(loadedTrade.holding_time_seconds));
      const ok = await fetchAllCharts(loadedTrade);
      if (ok === false) {
        addToast('error', 'Failed to load chart data');
      }
    } catch {
      addToast('error', 'Failed to load trade');
      navigate('/trades');
      setIsLoading(false);
      setIsChartLoading(false);
    }
  }, [id, addToast, navigate, fetchAllCharts]);

  async function handleRefreshChartData() {
    if (!trade) return;
    const ok = await fetchAllCharts(trade, true);
    if (ok === true) {
      addToast('success', 'Market data refreshed');
    } else if (ok === false) {
      addToast('error', 'Failed to refresh market data');
    }
  }

  useEffect(() => {
    fetchTrade();
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

  if (isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner size="lg" />
      </div>
    );
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
              title="Redownload market data for this trade day"
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
          />
        </div>

        {/* Media sidebar — same height as chart card */}
        <div className="card w-full lg:w-28 lg:self-stretch flex flex-col min-h-0 lg:max-h-[none]">
          <TradeMedia tradeId={trade.id} compact />
        </div>
      </div>

      {/* Wishful stop & Target price */}
      <div className="card p-4">
        <StopAnalysisFields
          tradeId={trade.id}
          trade={trade}
          onSaved={fetchTrade}
        />
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
              onChanged={fetchTrade}
            />
          </div>
          <div className="card p-4">
            <TradeNotes
              tradeId={trade.id}
              preTradeNotes={trade.pre_trade_notes}
              postTradeNotes={trade.post_trade_notes}
              onSaved={fetchTrade}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
