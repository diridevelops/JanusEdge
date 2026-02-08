import {
    createContext,
    useCallback,
    useMemo,
    useState,
    type ReactNode,
} from 'react';
import type { FilterParams } from '../types/common.types';

interface FilterState extends FilterParams {
  setFilters: (filters: Partial<FilterParams>) => void;
  clearFilters: () => void;
}

const defaultFilters: FilterParams = {
  account: undefined,
  symbol: undefined,
  side: undefined,
  tag: undefined,
  date_from: undefined,
  date_to: undefined,
};

export const FilterContext = createContext<FilterState>({
  ...defaultFilters,
  setFilters: () => {},
  clearFilters: () => {},
});

interface FilterProviderProps {
  children: ReactNode;
}

/** Provides global filter state for trades and analytics. */
export function FilterProvider({ children }: FilterProviderProps) {
  const [filters, setFiltersState] =
    useState<FilterParams>(defaultFilters);

  const setFilters = useCallback(
    (newFilters: Partial<FilterParams>) => {
      setFiltersState((prev) => ({ ...prev, ...newFilters }));
    },
    []
  );

  const clearFilters = useCallback(() => {
    setFiltersState(defaultFilters);
  }, []);

  const value = useMemo(
    () => ({
      ...filters,
      setFilters,
      clearFilters,
    }),
    [filters, setFilters, clearFilters]
  );

  return (
    <FilterContext.Provider value={value}>
      {children}
    </FilterContext.Provider>
  );
}
