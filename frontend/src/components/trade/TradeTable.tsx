import { Check } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listTags } from '../../api/tags.api';
import { useAuth } from '../../hooks/useAuth';
import type { Tag } from '../../types/marketData.types';
import type { Trade } from '../../types/trade.types';
import { formatCurrency, formatDateTime, formatDuration } from '../../utils/formatters';

interface TradeTableProps {
  /** Array of trades to display. */
  trades: Trade[];
  /** Current sort column. */
  sortBy: string;
  /** Current sort direction. */
  sortDir: 'asc' | 'desc';
  /** Callback when sort changes. */
  onSortChange: (column: string) => void;
}

const SORTABLE_COLUMNS = [
  { key: 'entry_time', label: 'Date' },
  { key: 'symbol', label: 'Symbol' },
  { key: 'side', label: 'Side' },
  { key: 'total_quantity', label: 'Qty' },
  { key: 'avg_entry_price', label: 'Entry' },
  { key: 'avg_exit_price', label: 'Exit' },
  { key: 'net_pnl', label: 'Net P&L' },
  { key: 'holding_time_seconds', label: 'Duration' },
] as const;

/** Sortable, filterable trade list table. */
export function TradeTable({ trades, sortBy, sortDir, onSortChange }: TradeTableProps) {
  const { user } = useAuth();
  const [tagMap, setTagMap] = useState<Map<string, Tag>>(new Map());

  const dateFormatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: user?.display_timezone ?? user?.timezone ?? 'UTC',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });

  let stripeIndex = -1;
  let previousDayKey = '';

  const rows = trades.map((trade) => {
    const dayKey = dateFormatter.format(new Date(trade.entry_time));
    if (dayKey !== previousDayKey) {
      stripeIndex += 1;
      previousDayKey = dayKey;
    }

    return {
      trade,
      rowClass:
        stripeIndex % 2 === 0
          ? 'bg-white hover:bg-gray-100'
          : 'bg-gray-50/70 hover:bg-gray-100/70',
    };
  });

  useEffect(() => {
    listTags()
      .then((tags) => {
        const map = new Map<string, Tag>();
        for (const tag of tags) {
          map.set(tag.id, tag);
        }
        setTagMap(map);
      })
      .catch(() => {
        // Tag lookup failure is non-critical
      });
  }, []);

  function renderSortIndicator(column: string) {
    if (sortBy !== column) return null;
    return <span className="ml-1">{sortDir === 'asc' ? '▲' : '▼'}</span>;
  }

  if (trades.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p className="text-lg font-medium">No trades found</p>
        <p className="mt-1 text-sm">Try adjusting your filters or import some trades.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto border border-gray-200 rounded-lg">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {SORTABLE_COLUMNS.map((col) => (
              <th
                key={col.key}
                onClick={() => onSortChange(col.key)}
                className="px-4 py-2.5 text-left font-medium text-gray-500 uppercase tracking-wider text-xs cursor-pointer hover:text-gray-700 select-none whitespace-nowrap"
              >
                {col.label}
                {renderSortIndicator(col.key)}
              </th>
            ))}
            <th className="px-4 py-2.5 text-left font-medium text-gray-500 uppercase tracking-wider text-xs whitespace-nowrap">
              Tags
            </th>
            <th className="px-4 py-2.5 text-center font-medium text-gray-500 uppercase tracking-wider text-xs whitespace-nowrap">
              MKT DATA
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map(({ trade, rowClass }) => (
            <tr key={trade.id} className={rowClass}>
              <td className="px-4 py-2.5 whitespace-nowrap">
                <Link
                  to={`/trades/${trade.id}`}
                  className="text-brand-600 hover:text-brand-800 font-medium"
                >
                  {formatDateTime(trade.entry_time, user?.display_timezone)}
                </Link>
              </td>
              <td className="px-4 py-2.5 font-medium text-gray-900">
                {trade.symbol}
              </td>
              <td className="px-4 py-2.5">
                <span
                  className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                    trade.side === 'Long'
                      ? 'bg-green-50 text-green-700'
                      : 'bg-red-50 text-red-700'
                  }`}
                >
                  {trade.side}
                </span>
              </td>
              <td className="px-4 py-2.5 text-right text-gray-900">
                {trade.total_quantity}
              </td>
              <td className="px-4 py-2.5 text-right text-gray-900">
                {formatCurrency(trade.avg_entry_price)}
              </td>
              <td className="px-4 py-2.5 text-right text-gray-900">
                {formatCurrency(trade.avg_exit_price)}
              </td>
              <td
                className={`px-4 py-2.5 text-right font-semibold ${
                  trade.net_pnl >= 0 ? 'text-profit' : 'text-loss'
                }`}
              >
                {formatCurrency(trade.net_pnl)}
              </td>
              <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">
                {formatDuration(trade.holding_time_seconds)}
              </td>
              <td className="px-4 py-2.5">
                <div className="flex flex-wrap gap-1">
                  {trade.tag_ids.map((tagId) => {
                    const tag = tagMap.get(tagId);
                    if (!tag) return null;
                    return (
                      <span
                        key={tagId}
                        className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium"
                        style={{
                          backgroundColor: tag.color + '20',
                          color: tag.color,
                        }}
                      >
                        {tag.name}
                      </span>
                    );
                  })}
                </div>
              </td>
              <td className="px-4 py-2.5 text-center">
                {trade.market_data_cached ? (
                  <Check className="h-4 w-4 text-green-600 inline" aria-label="Market data cached" />
                ) : (
                  <span className="text-gray-300">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
