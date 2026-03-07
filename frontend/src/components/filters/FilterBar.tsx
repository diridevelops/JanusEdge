import { useEffect, useState } from 'react';
import { listAccounts } from '../../api/accounts.api';
import { listTags } from '../../api/tags.api';
import { getSymbols } from '../../api/trades.api';
import type { TradeAccount } from '../../types/account.types';
import type { Tag } from '../../types/marketData.types';

interface FilterBarProps {
  /** Current filter values. */
  filters: {
    symbol: string;
    side: string;
    account: string;
    tag: string;
    date_from: string;
    date_to: string;
  };
  /** Callback when any filter changes. */
  onFilterChange: (key: string, value: string) => void;
  /** Callback to clear all filters. */
  onClearFilters: () => void;
  /** When true, a symbol must be selected (no "All" option). */
  requireSymbol?: boolean;
  /** When false, hides the date range inputs while preserving shared filter shape. */
  showDateFilters?: boolean;
}

/** Global filter toolbar for trade list and analytics pages. */
export function FilterBar({
  filters,
  onFilterChange,
  onClearFilters,
  requireSymbol = false,
  showDateFilters = true,
}: FilterBarProps) {
  const [accounts, setAccounts] = useState<TradeAccount[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);

  useEffect(() => {
    listAccounts()
      .then(setAccounts)
      .catch(() => {});
    listTags()
      .then(setTags)
      .catch(() => {});
    getSymbols()
      .then((syms) => {
        setSymbols(syms);
        // Auto-select first symbol when required and none selected
        if (requireSymbol && !filters.symbol && syms.length > 0) {
          onFilterChange('symbol', syms[0]!);
        }
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const hasActiveFilters = Object.values(filters).some((v) => v !== '');

  return (
    <div className="flex flex-wrap items-end gap-3 bg-gray-50 p-4 rounded-lg dark:bg-gray-800/50">
      {/* Symbol */}
      <div>
        <label htmlFor="filter-symbol" className="block text-xs font-medium text-gray-500 mb-1 dark:text-gray-400">
          Symbol
        </label>
        <select
          id="filter-symbol"
          value={filters.symbol}
          onChange={(e) => onFilterChange('symbol', e.target.value)}
          className="input-field w-28 text-sm"
        >
          {!requireSymbol && <option value="">All</option>}
          {symbols.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Side */}
      <div>
        <label htmlFor="filter-side" className="block text-xs font-medium text-gray-500 mb-1 dark:text-gray-400">
          Side
        </label>
        <select
          id="filter-side"
          value={filters.side}
          onChange={(e) => onFilterChange('side', e.target.value)}
          className="input-field w-28 text-sm"
        >
          <option value="">All</option>
          <option value="Long">Long</option>
          <option value="Short">Short</option>
        </select>
      </div>

      {/* Account */}
      <div>
        <label htmlFor="filter-account" className="block text-xs font-medium text-gray-500 mb-1 dark:text-gray-400">
          Account
        </label>
        <select
          id="filter-account"
          value={filters.account}
          onChange={(e) => onFilterChange('account', e.target.value)}
          className="input-field w-40 text-sm"
        >
          <option value="">All Accounts</option>
          {accounts.map((acc) => (
            <option key={acc.id} value={acc.id}>
              {acc.display_name || acc.account_name}
            </option>
          ))}
        </select>
      </div>

      {/* Tag */}
      <div>
        <label htmlFor="filter-tag" className="block text-xs font-medium text-gray-500 mb-1 dark:text-gray-400">
          Tag
        </label>
        <select
          id="filter-tag"
          value={filters.tag}
          onChange={(e) => onFilterChange('tag', e.target.value)}
          className="input-field w-36 text-sm"
        >
          <option value="">All Tags</option>
          {tags.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </div>

      {showDateFilters && (
        <>
          {/* Date from */}
          <div>
            <label htmlFor="filter-date-from" className="block text-xs font-medium text-gray-500 mb-1 dark:text-gray-400">
              From
            </label>
            <input
              id="filter-date-from"
              type="date"
              value={filters.date_from}
              onChange={(e) => onFilterChange('date_from', e.target.value)}
              className="input-field w-36 text-sm"
            />
          </div>

          {/* Date to */}
          <div>
            <label htmlFor="filter-date-to" className="block text-xs font-medium text-gray-500 mb-1 dark:text-gray-400">
              To
            </label>
            <input
              id="filter-date-to"
              type="date"
              value={filters.date_to}
              onChange={(e) => onFilterChange('date_to', e.target.value)}
              className="input-field w-36 text-sm"
            />
          </div>
        </>
      )}

      {/* Clear */}
      {hasActiveFilters && (
        <button
          onClick={onClearFilters}
          className="text-sm text-gray-500 hover:text-gray-700 underline pb-0.5 dark:text-gray-400 dark:hover:text-gray-200"
        >
          Clear Filters
        </button>
      )}
    </div>
  );
}
