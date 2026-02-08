import { useContext } from 'react';
import { FilterContext } from '../contexts/FilterContext';

/**
 * Hook for accessing and modifying global filter state.
 *
 * @returns Filter context with current filters and setter.
 */
export function useFilters() {
  return useContext(FilterContext);
}
