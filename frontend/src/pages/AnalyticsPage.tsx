import { useCallback, useEffect, useState } from 'react';

import {
    getDrawdown,
    getSummary,
} from '../api/analytics.api';
import { StatsGrid } from '../components/analytics/StatsGrid';
import { FilterBar } from '../components/filters/FilterBar';
import { useAuth } from '../hooks/useAuth';
import type {
    AnalyticsSummary,
    DrawdownPoint,
} from '../types/analytics.types';

/** Analytics page with detailed summary metrics. */
export function AnalyticsPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState({
    symbol: '',
    side: '',
    account: '',
    tag: '',
    date_from: '',
    date_to: '',
  });
  const [loading, setLoading] = useState(true);

  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [drawdown, setDrawdown] = useState<DrawdownPoint[]>([]);

  type Filters = typeof filters;
  const fetchData = useCallback(async (f: Filters) => {
    setLoading(true);
    const apiFilters = Object.fromEntries(
      Object.entries(f).filter(([, v]) => v !== '')
    );
    try {
      const [summaryRes, drawdownRes] = await Promise.all([
        getSummary(apiFilters),
        getDrawdown(apiFilters),
      ]);

      setSummary(summaryRes);
      setDrawdown(drawdownRes);
    } catch {
      // Toast handled by Axios interceptor for 401; silent catch otherwise
    } finally {
      setLoading(false);
    }
  }, [user?.display_timezone, user?.timezone]);

  useEffect(() => {
    void fetchData(filters);
  }, [filters, fetchData]);

  function handleFilterChange(key: string, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  function handleClearFilters() {
    setFilters({ symbol: '', side: '', account: '', tag: '', date_from: '', date_to: '' });
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Analytics</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Detailed performance metrics and risk analysis of your trading.
        </p>
      </div>

      {/* Filters */}
      <FilterBar filters={filters} onFilterChange={handleFilterChange} onClearFilters={handleClearFilters} />

      {/* Summary metrics */}
      <StatsGrid
        summary={summary}
        drawdown={drawdown}
        isLoading={loading}
      />
    </div>
  );
}
