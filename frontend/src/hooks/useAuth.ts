import { useContext } from 'react';
import { AuthContext } from '../contexts/AuthContext';

/**
 * Hook for accessing authentication state and actions.
 *
 * @returns Auth context containing user, token, and auth methods.
 */
export function useAuth() {
  return useContext(AuthContext);
}
