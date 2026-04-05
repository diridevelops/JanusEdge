import axios from 'axios';
import type { AuthResponse } from '../types/auth.types';
import {
  clearAccessToken,
  getAccessToken,
  notifyAuthResponse,
  notifyUnauthorized,
  setAccessToken,
} from './authSession';

/**
 * Axios instance configured for the Janus Edge API.
 *
 * - Base URL set from env or defaults to '/api'.
 * - Request interceptor attaches the short-lived access token.
 * - Response interceptor refreshes once on 401, then clears auth if needed.
 */
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

const refreshClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

let refreshPromise: Promise<AuthResponse> | null = null;

/** Attach the access token on every request if available. */
apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/** Handle 401 errors with one refresh-and-retry attempt. */
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as
      | (typeof error.config & { _retry?: boolean })
      | undefined;

    if (
      error.response?.status !== 401
      || !originalRequest
      || originalRequest._retry
      || originalRequest.url?.includes('/auth/login')
      || originalRequest.url?.includes('/auth/register')
      || originalRequest.url?.includes('/auth/refresh')
      || originalRequest.url?.includes('/auth/logout')
    ) {
      if (error.response?.status === 401) {
        clearAccessToken();
        notifyUnauthorized();
      }
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    try {
      if (!refreshPromise) {
        refreshPromise = refreshClient
          .post<AuthResponse>('/auth/refresh')
          .then((response) => response.data)
          .finally(() => {
            refreshPromise = null;
          });
      }

      const authResponse = await refreshPromise;
      setAccessToken(authResponse.token);
      notifyAuthResponse(authResponse);
      originalRequest.headers = originalRequest.headers ?? {};
      originalRequest.headers.Authorization = `Bearer ${authResponse.token}`;
      return apiClient(originalRequest);
    } catch (refreshError) {
      clearAccessToken();
      notifyUnauthorized();
      return Promise.reject(refreshError);
    }
  }
);

export default apiClient;
