import { useContext } from 'react';
import { ClientConfigContext } from '../contexts/ClientConfigContext';

/** Hook for accessing public backend-driven client config. */
export function useClientConfig() {
  return useContext(ClientConfigContext);
}
