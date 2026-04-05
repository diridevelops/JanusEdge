import {
    createContext,
    useCallback,
    useEffect,
    useMemo,
    useState,
    type ReactNode,
} from 'react';
import * as authApi from '../api/auth.api';
import {
  clearAccessToken,
  getAccessToken,
  registerAuthEventHandlers,
  setAccessToken,
} from '../api/authSession';
import type { AuthResponse } from '../types/auth.types';
import type { User } from '../types/auth.types';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (
    username: string,
    password: string,
    timezone: string
  ) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

export const AuthContext = createContext<AuthState>({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true,
  login: async () => {},
  register: async () => {},
  logout: () => {},
  refreshProfile: async () => {},
});

interface AuthProviderProps {
  children: ReactNode;
}

let initialSessionRestorePromise:
  | Promise<AuthResponse | null>
  | null = null;

function restoreInitialSession(): Promise<AuthResponse | null> {
  if (!initialSessionRestorePromise) {
    initialSessionRestorePromise = authApi
      .refreshSession()
      .catch(() => null);
    initialSessionRestorePromise.finally(() => {
      initialSessionRestorePromise = null;
    });
  }

  return initialSessionRestorePromise;
}

/** Provides authentication state to the entire app. */
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(
    () => getAccessToken()
  );
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isActive = true;

    const unregisterHandlers = registerAuthEventHandlers({
      onAuthResponse: (response) => {
        if (!isActive) {
          return;
        }
        setAccessToken(response.token);
        setToken(response.token);
        setUser(response.user);
      },
      onUnauthorized: () => {
        if (!isActive) {
          return;
        }
        clearAccessToken();
        setToken(null);
        setUser(null);
      },
    });

    restoreInitialSession()
      .then((response) => {
        if (!isActive) {
          return;
        }

        if (!response) {
          clearAccessToken();
          setToken(null);
          setUser(null);
          return;
        }

        setAccessToken(response.token);
        setToken(response.token);
        setUser(response.user);
      })
      .finally(() => {
        if (isActive) {
          setIsLoading(false);
        }
      });

    return () => {
      isActive = false;
      unregisterHandlers();
    };
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await authApi.login({ username, password });
      setAccessToken(res.token);
      setToken(res.token);
      setUser(res.user);
    },
    []
  );

  const register = useCallback(
    async (username: string, password: string, timezone: string) => {
      const res = await authApi.register({
        username,
        password,
        timezone,
      });
      setAccessToken(res.token);
      setToken(res.token);
      setUser(res.user);
    },
    []
  );

  const logout = useCallback(() => {
    authApi.logout().catch(() => {
      // Ignore errors on logout
    });
    clearAccessToken();
    setToken(null);
    setUser(null);
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      const profile = await authApi.getProfile();
      setUser(profile);
    } catch {
      // Silently fail; auth recovery is handled centrally
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      token,
      isAuthenticated: !!token && !!user,
      isLoading,
      login,
      register,
      logout,
      refreshProfile,
    }),
    [user, token, isLoading, login, register, logout, refreshProfile]
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}
