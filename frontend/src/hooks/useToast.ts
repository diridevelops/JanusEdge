import { useContext } from 'react';
import { ToastContext } from '../contexts/ToastContext';

/**
 * Hook for accessing toast notification actions.
 *
 * @returns Toast context with addToast and removeToast.
 */
export function useToast() {
  return useContext(ToastContext);
}
