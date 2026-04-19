import apiClient from './client';
import type {
  AuthResponse,
  ExportBackupFile,
  LoginRequest,
  MarketDataMappings,
  RegisterRequest,
  RestoreBackupResponse,
  SymbolMappings,
  User,
} from '../types/auth.types';
import { BACKUP_FILENAME } from '../utils/constants';

function getDownloadFilename(contentDisposition?: string): string {
  if (!contentDisposition) {
    return BACKUP_FILENAME;
  }

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }

  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  if (filenameMatch?.[1]) {
    return filenameMatch[1];
  }

  return BACKUP_FILENAME;
}

/** Register a new user account. */
export async function register(
  data: RegisterRequest
): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>(
    '/auth/register',
    data
  );
  return res.data;
}

/** Login with username and password. */
export async function login(
  data: LoginRequest
): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>(
    '/auth/login',
    data
  );
  return res.data;
}

/** Restore or rotate the current browser session. */
export async function refreshSession(): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>('/auth/refresh');
  return res.data;
}

/** Logout the current user. */
export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout');
}

/** Get the current user profile. */
export async function getProfile(): Promise<User> {
  const res = await apiClient.get<User>('/auth/me');
  return res.data;
}

/** Change the current user's password. */
export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<{ message: string }> {
  const res = await apiClient.post<{ message: string }>(
    '/auth/change-password',
    { current_password: currentPassword, new_password: newPassword }
  );
  return res.data;
}

/** Update the current user's trading timezone. */
export async function updateTimezone(
  timezone: string
): Promise<User> {
  const res = await apiClient.put<User>('/auth/timezone', { timezone });
  return res.data;
}

/** Update the current user's display timezone. */
export async function updateDisplayTimezone(
  displayTimezone: string
): Promise<User> {
  const res = await apiClient.put<User>('/auth/display-timezone', {
    display_timezone: displayTimezone,
  });
  return res.data;
}

/** Update the current user's starting equity for simulations. */
export async function updateStartingEquity(
  startingEquity: number
): Promise<User> {
  const res = await apiClient.put<User>('/auth/starting-equity', {
    starting_equity: startingEquity,
  });
  return res.data;
}

/** Update the current user's symbol mappings. */
export async function updateSymbolMappings(
  symbolMappings: SymbolMappings
): Promise<User> {
  const res = await apiClient.put<User>('/auth/symbol-mappings', {
    symbol_mappings: symbolMappings,
  });
  return res.data;
}

/** Update the current user's market-data symbol mappings. */
export async function updateMarketDataMappings(
  marketDataMappings: MarketDataMappings
): Promise<User> {
  const res = await apiClient.put<User>('/auth/market-data-mappings', {
    market_data_mappings: marketDataMappings,
  });
  return res.data;
}

/** Download a portable backup ZIP for the current user. */
export async function exportBackup(): Promise<ExportBackupFile> {
  const res = await apiClient.get<Blob>('/auth/export', {
    responseType: 'blob',
  });

  return {
    blob: res.data,
    filename: getDownloadFilename(res.headers['content-disposition']),
  };
}

/** Restore a portable backup ZIP into the current user account. */
export async function restoreBackup(
  file: File
): Promise<RestoreBackupResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await apiClient.post<RestoreBackupResponse>(
    '/auth/restore',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );

  return res.data;
}
