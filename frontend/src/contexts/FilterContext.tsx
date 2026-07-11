import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useAuth } from '../hooks/useAuth';
import type { FilterParams } from '../types/common.types';

export type FilterValues = Required<FilterParams>;

interface FilterState {
  filters: FilterValues;
  isReady: boolean;
  setFilters: (filters: Partial<FilterParams>) => void;
  replaceFilters: (filters: Partial<FilterParams>) => void;
  clearFilters: () => void;
}

const STORAGE_PREFIX = 'janusedge:filters:v1:';
const defaultFilters: FilterValues = {
  account: '', symbol: '', side: '', tag: '', date_from: '', date_to: '',
};
const FILTER_KEYS = Object.keys(defaultFilters) as Array<keyof FilterValues>;

function normalizeFilters(filters: Partial<FilterParams>): FilterValues {
  return FILTER_KEYS.reduce<FilterValues>((result, key) => {
    const value = filters[key];
    result[key] = typeof value === 'string' ? value : '';
    return result;
  }, { ...defaultFilters });
}

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}${userId}`;
}

function loadFilters(userId: string): FilterValues {
  try {
    const raw = window.localStorage.getItem(storageKey(userId));
    if (!raw) return { ...defaultFilters };
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('Invalid filter storage');
    }
    return normalizeFilters(parsed as Partial<FilterParams>);
  } catch {
    window.localStorage.removeItem(storageKey(userId));
    return { ...defaultFilters };
  }
}

export const FilterContext = createContext<FilterState>({
  filters: defaultFilters,
  isReady: false,
  setFilters: () => {},
  replaceFilters: () => {},
  clearFilters: () => {},
});

interface FilterProviderProps { children: ReactNode; }

/** Provides persisted, user-scoped filters shared by filter pages. */
export function FilterProvider({ children }: FilterProviderProps) {
  const { user, isLoading } = useAuth();
  const [filters, setFiltersState] = useState<FilterValues>(defaultFilters);
  const [isReady, setIsReady] = useState(false);
  const userId = user?.id;

  useEffect(() => {
    if (isLoading) {
      setIsReady(false);
      return;
    }
    setFiltersState(userId ? loadFilters(userId) : { ...defaultFilters });
    setIsReady(true);
  }, [isLoading, userId]);

  const persist = useCallback((nextFilters: FilterValues) => {
    if (userId) {
      window.localStorage.setItem(storageKey(userId), JSON.stringify(nextFilters));
    }
  }, [userId]);

  const setFilters = useCallback((updates: Partial<FilterParams>) => {
    setFiltersState((previous) => {
      const next = normalizeFilters({ ...previous, ...updates });
      persist(next);
      return next;
    });
  }, [persist]);

  const replaceFilters = useCallback((nextFilters: Partial<FilterParams>) => {
    const next = normalizeFilters(nextFilters);
    setFiltersState(next);
    persist(next);
  }, [persist]);

  const clearFilters = useCallback(() => {
    setFiltersState({ ...defaultFilters });
    if (userId) window.localStorage.removeItem(storageKey(userId));
  }, [userId]);

  const value = useMemo(() => ({
    filters, isReady, setFilters, replaceFilters, clearFilters,
  }), [filters, isReady, setFilters, replaceFilters, clearFilters]);

  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>;
}
