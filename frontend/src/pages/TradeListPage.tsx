import { List, Plus, Upload } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { listTrades } from '../api/trades.api';
import { FilterBar } from '../components/filters/FilterBar';
import { TradeTable } from '../components/trade/TradeTable';
import { PageHeader } from '../components/ui/PageHeader';
import { Pagination } from '../components/ui/Pagination';
import { Spinner } from '../components/ui/Spinner';
import { useToast } from '../hooks/useToast';
import type { Trade } from '../types/trade.types';
import { DEFAULT_PAGE_SIZE } from '../utils/constants';

/** Trade list page — filterable, sortable table of trades. */
export function TradeListPage() {
  const location = useLocation();
  const navigate = useNavigate();

  type TradeFilters = {
    symbol: string;
    side: string;
    account: string;
    tag: string;
    date_from: string;
    date_to: string;
  };

  const areFiltersEqual = useCallback(
    (left: TradeFilters, right: TradeFilters) =>
      left.symbol === right.symbol
      && left.side === right.side
      && left.account === right.account
      && left.tag === right.tag
      && left.date_from === right.date_from
      && left.date_to === right.date_to,
    []
  );

  const getFiltersFromSearch = useCallback((search: string) => {
    const params = new URLSearchParams(search);
    return {
      symbol: params.get('symbol') ?? '',
      side: params.get('side') ?? '',
      account: params.get('account') ?? '',
      tag: params.get('tag') ?? '',
      date_from: params.get('date_from') ?? '',
      date_to: params.get('date_to') ?? '',
    };
  }, []);

  const buildSearchFromFilters = useCallback((nextFilters: TradeFilters) => {
    const params = new URLSearchParams();
    Object.entries(nextFilters).forEach(([key, value]) => {
      if (value !== '') {
        params.set(key, value);
      }
    });
    return params.toString();
  }, []);

  const [trades, setTrades] = useState<Trade[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [sortBy, setSortBy] = useState('entry_time');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [filters, setFilters] = useState(() => getFiltersFromSearch(location.search));
  const { addToast } = useToast();

  useEffect(() => {
    const nextFilters = getFiltersFromSearch(location.search);
    setFilters((prev) => {
      if (areFiltersEqual(prev, nextFilters)) {
        return prev;
      }
      setPage(1);
      return nextFilters;
    });
  }, [location.search, getFiltersFromSearch, areFiltersEqual]);

  useEffect(() => {
    const currentSearch = location.search.startsWith('?')
      ? location.search.slice(1)
      : location.search;
    const nextSearch = buildSearchFromFilters(filters);

    if (currentSearch === nextSearch) {
      return;
    }

    navigate(
      {
        pathname: location.pathname,
        search: nextSearch ? `?${nextSearch}` : '',
      },
      { replace: true }
    );
  }, [filters, buildSearchFromFilters, navigate, location.pathname, location.search]);

  const fetchTrades = useCallback(async () => {
    setIsLoading(true);
    try {
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
    } catch {
      addToast('error', 'Failed to load trades');
    } finally {
      setIsLoading(false);
    }
  }, [page, sortBy, sortDir, filters, addToast]);

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
    setFilters(getFiltersFromSearch(''));
    setPage(1);
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <PageHeader
          icon={List}
          title="Trades"
          description={`${totalItems} ${totalItems === 1 ? 'trade' : 'trades'} total`}
          descriptionClassName="mt-0.5 text-sm text-gray-500 dark:text-gray-400"
        />
        <div className="flex items-center gap-2">
          <Link to="/import" className="btn-primary text-sm inline-flex items-center gap-1">
            Import <Upload className="h-4 w-4" />
          </Link>
          <Link to="/trades/new" className="btn-primary inline-flex items-center gap-1.5">
            <Plus className="h-4 w-4" />
            New Trade
          </Link>
        </div>
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
