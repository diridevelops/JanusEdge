import { ArrowLeft, RefreshCw, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { listExecutions } from '../api/executions.api';
import { getOHLC } from '../api/marketData.api';
import { deleteTrade, getTrade } from '../api/trades.api';
import { CandlestickChart } from '../components/charts/CandlestickChart';
import { ExecutionList } from '../components/trade/ExecutionList';
import { TagSelector } from '../components/trade/TagSelector';
import { TradeNotes } from '../components/trade/TradeNotes';
import { Spinner } from '../components/ui/Spinner';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import type { Execution } from '../types/execution.types';
import type { ChartInterval, OHLCDataPoint } from '../types/marketData.types';
import type { Trade } from '../types/trade.types';
import { formatCurrency, formatDateTime, formatDuration } from '../utils/formatters';

/** Trade detail page — chart, executions, notes, tags. */
export function TradeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { addToast } = useToast();
  const { user } = useAuth();

  const [trade, setTrade] = useState<Trade | null>(null);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [ohlcData, setOhlcData] = useState<OHLCDataPoint[]>([]);
  const [interval, setInterval] = useState<ChartInterval>('5m');
  const [isLoading, setIsLoading] = useState(true);
  const [isChartLoading, setIsChartLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchTrade = useCallback(async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const [tradeData, execData] = await Promise.all([
        getTrade(id),
        listExecutions({ trade_id: id }),
      ]);
      setTrade(tradeData.trade);
      setExecutions(execData.executions ?? execData.items);
    } catch {
      addToast('error', 'Failed to load trade');
      navigate('/trades');
    } finally {
      setIsLoading(false);
    }
  }, [id, addToast, navigate]);

  const fetchChart = useCallback(async (forceRefresh: boolean = false) => {
    if (!trade) return false;
    setIsChartLoading(true);
    let succeeded = true;
    try {
      const entryDate = new Date(trade.entry_time);
      const exitDate = new Date(trade.exit_time);

      const first = entryDate <= exitDate ? entryDate : exitDate;
      const last = entryDate <= exitDate ? exitDate : entryDate;

      const dayStart = new Date(
        Date.UTC(
          first.getUTCFullYear(),
          first.getUTCMonth(),
          first.getUTCDate(),
          0,
          0,
          0,
          0
        )
      );

      const dayEnd = new Date(
        Date.UTC(
          last.getUTCFullYear(),
          last.getUTCMonth(),
          last.getUTCDate() + 1,
          0,
          0,
          0,
          0
        )
      );

      const data = await getOHLC({
        symbol: trade.symbol,
        interval,
        start: dayStart.toISOString(),
        end: dayEnd.toISOString(),
        force_refresh: forceRefresh,
      });
      setOhlcData(data);
    } catch {
      // Chart data may not be available for all symbols
      succeeded = false;
      setOhlcData([]);
    } finally {
      setIsChartLoading(false);
    }
    return succeeded;
  }, [trade, interval]);

  async function handleRefreshChartData() {
    const ok = await fetchChart(true);
    if (ok) {
      addToast('success', 'Market data refreshed');
    } else {
      addToast('error', 'Failed to refresh market data');
    }
  }

  useEffect(() => {
    fetchTrade();
  }, [fetchTrade]);

  useEffect(() => {
    if (trade) {
      fetchChart();
    }
  }, [trade, fetchChart]);

  async function handleDelete() {
    if (!id || !confirm('Delete this trade? It can be restored later.')) return;
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
      <div className="text-center py-24 text-gray-500">
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
            className="text-gray-400 hover:text-gray-600"
            aria-label="Back to trades"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {trade.symbol}{' '}
              <span
                className={`text-lg ${trade.side === 'Long' ? 'text-green-600' : 'text-red-600'}`}
              >
                {trade.side}
              </span>
            </h1>
            <p className="text-sm text-gray-500">
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
            <p className="text-xs text-gray-500 uppercase">Quantity</p>
            <p className="font-semibold text-gray-900">{trade.total_quantity}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase">Avg Entry</p>
            <p className="font-semibold text-gray-900">{formatCurrency(trade.avg_entry_price)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase">Avg Exit</p>
            <p className="font-semibold text-gray-900">{formatCurrency(trade.avg_exit_price)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase">Gross P&L</p>
            <p className={`font-semibold ${trade.gross_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
              {formatCurrency(trade.gross_pnl)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase">Fees</p>
            <p className="font-semibold text-gray-700">{formatCurrency(trade.fee)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase">Net P&L</p>
            <p className={`font-bold ${trade.net_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
              {formatCurrency(trade.net_pnl)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase">Initial Risk</p>
            <p className="font-semibold text-gray-900">
              {trade.initial_risk > 0
                ? formatCurrency(trade.initial_risk)
                : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase">R-multiple</p>
            <p className={`font-semibold ${trade.net_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
              {trade.initial_risk > 0
                ? `${(trade.net_pnl / trade.initial_risk).toFixed(2)}R`
                : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase">Duration</p>
            <p className="font-semibold text-gray-900">
              {formatDuration(trade.holding_time_seconds)}
            </p>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">
            Price Chart
          </h2>
          <button
            type="button"
            onClick={handleRefreshChartData}
            disabled={isChartLoading}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-800 disabled:opacity-50"
            title="Redownload market data for this trade day"
          >
            <RefreshCw className={`h-4 w-4 ${isChartLoading ? 'animate-spin' : ''}`} />
            Refresh Data
          </button>
        </div>
        <CandlestickChart
          ohlcData={ohlcData}
          executions={executions}
          interval={interval}
          onIntervalChange={setInterval}
          avgEntryPrice={trade.avg_entry_price}
          avgExitPrice={trade.avg_exit_price}
          isLoading={isChartLoading}
          displayTimezone={user?.display_timezone ?? user?.timezone}
        />
      </div>

      {/* Lower section: Executions + Notes/Tags */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Executions */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-3">
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
