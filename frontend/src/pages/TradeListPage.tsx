import { Plus, Search } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listTrades, searchTrades } from '../api/trades.api';
import { FilterBar } from '../components/filters/FilterBar';
import { TradeTable } from '../components/trade/TradeTable';
import { Pagination } from '../components/ui/Pagination';
import { Spinner } from '../components/ui/Spinner';
import { useDebounce } from '../hooks/useDebounce';
import { useToast } from '../hooks/useToast';
import type { Trade } from '../types/trade.types';
import { DEFAULT_PAGE_SIZE } from '../utils/constants';

/** Trade list page — filterable, sortable table of trades. */
export function TradeListPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [sortBy, setSortBy] = useState('entry_time');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState({
    symbol: '',
    side: '',
    account: '',
    tag: '',
    date_from: '',
    date_to: '',
  });
  const debouncedSearch = useDebounce(searchQuery, 300);
  const { addToast } = useToast();

  const fetchTrades = useCallback(async () => {
    setIsLoading(true);
    try {
      if (debouncedSearch) {
        const results = await searchTrades(debouncedSearch);
        setTrades(results);
        setTotalPages(1);
        setTotalItems(results.length);
      } else {
        const result = await listTrades({
          page,
          per_page: DEFAULT_PAGE_SIZE,
          sort_by: sortBy,
          sort_dir: sortDir,
          ...Object.fromEntries(
            Object.entries(filters).filter(([, v]) => v !== '')
          ),
        });
        setTrades(result.trades ?? result.items);
        setTotalPages(result.pages);
        setTotalItems(result.total);
      }
    } catch {
      addToast('error', 'Failed to load trades');
    } finally {
      setIsLoading(false);
    }
  }, [page, sortBy, sortDir, filters, debouncedSearch, addToast]);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  function handleSortChange(column: string) {
    if (sortBy === column) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(column);
      setSortDir('desc');
    }
    setPage(1);
  }

  function handleFilterChange(key: string, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  }

  function handleClearFilters() {
    setFilters({
      symbol: '',
      side: '',
      account: '',
      tag: '',
      date_from: '',
      date_to: '',
    });
    setSearchQuery('');
    setPage(1);
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Trades</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            {totalItems} {totalItems === 1 ? 'trade' : 'trades'} total
          </p>
        </div>
        <Link to="/trades/new" className="btn-primary inline-flex items-center gap-1.5">
          <Plus className="h-4 w-4" />
          New Trade
        </Link>
      </div>

      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search trades by symbol, tags, notes..."
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setPage(1);
          }}
          className="input-field pl-10 text-sm"
        />
      </div>

      {/* Filters */}
      <FilterBar
        filters={filters}
        onFilterChange={handleFilterChange}
        onClearFilters={handleClearFilters}
      />

      {/* Trade table */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : (
        <>
          <TradeTable
            trades={trades}
            sortBy={sortBy}
            sortDir={sortDir}
            onSortChange={handleSortChange}
          />
          {totalPages > 1 && (
            <Pagination
              page={page}
              pages={totalPages}
              onPageChange={setPage}
            />
          )}
        </>
      )}
    </div>
  );
}
