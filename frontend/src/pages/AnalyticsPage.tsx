import { BarChart3 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import {
    getDrawdown,
    getSummary,
} from '../api/analytics.api';
import { StatsGrid } from '../components/analytics/StatsGrid';
import { FilterBar } from '../components/filters/FilterBar';
import { PageHeader } from '../components/ui/PageHeader';
import { useAuth } from '../hooks/useAuth';
import { useFilters } from '../hooks/useFilters';
import type {
    AnalyticsSummary,
    DrawdownPoint,
} from '../types/analytics.types';

/** Analytics page with detailed summary metrics. */
export function AnalyticsPage() {
  const { user } = useAuth();
  const { filters, isReady, setFilters, clearFilters } = useFilters();
  const [loading, setLoading] = useState(true);

  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [drawdown, setDrawdown] = useState<DrawdownPoint[]>([]);

  const fetchData = useCallback(async (f: typeof filters) => {
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
    if (!isReady) return;
    void fetchData(filters);
  }, [filters, fetchData, isReady]);

  function handleFilterChange(key: string, value: string) {
    setFilters({ [key]: value });
  }

  function handleClearFilters() {
    clearFilters();
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <PageHeader
        icon={BarChart3}
        title="Analytics"
        description="Detailed performance metrics and risk analysis of your trading."
      />

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
