import axios from 'axios';
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getClientConfig } from '../api/clientConfig.api';
import type { ClientConfig } from '../types/clientConfig.types';

interface ClientConfigState {
  clientConfig: ClientConfig | null;
  isLoading: boolean;
  loadError: string | null;
  refreshClientConfig: () => Promise<void>;
}

export const ClientConfigContext = createContext<ClientConfigState>({
  clientConfig: null,
  isLoading: true,
  loadError: null,
  refreshClientConfig: async () => {},
});

interface ClientConfigProviderProps {
  children: ReactNode;
}

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const apiMessage =
      error.response?.data?.error?.message ?? error.response?.data?.message;
    if (typeof apiMessage === 'string' && apiMessage.trim()) {
      return apiMessage;
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return 'Failed to load app config.';
}

/** Provides public backend-driven config to the application. */
export function ClientConfigProvider({
  children,
}: ClientConfigProviderProps) {
  const [clientConfig, setClientConfig] = useState<ClientConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refreshClientConfig = useCallback(async () => {
    try {
      const nextConfig = await getClientConfig();
      setClientConfig(nextConfig);
      setLoadError(null);
    } catch (error: unknown) {
      setLoadError(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshClientConfig();
  }, [refreshClientConfig]);

  const value = useMemo(
    () => ({
      clientConfig,
      isLoading,
      loadError,
      refreshClientConfig,
    }),
    [clientConfig, isLoading, loadError, refreshClientConfig]
  );

  return (
    <ClientConfigContext.Provider value={value}>
      {children}
    </ClientConfigContext.Provider>
  );
}
