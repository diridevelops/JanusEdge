import { useEffect, useState } from 'react';

/**
 * Debounce a value by the given delay.
 *
 * @param value - The value to debounce.
 * @param delay - Delay in milliseconds (default 300ms).
 * @returns The debounced value.
 */
export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
