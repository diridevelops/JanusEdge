import { useContext } from 'react';
import { ThemeContext } from '../contexts/ThemeContext';

/** Hook to access the current theme and toggle function. */
export function useTheme() {
  return useContext(ThemeContext);
}
