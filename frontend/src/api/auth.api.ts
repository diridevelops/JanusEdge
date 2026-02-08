import apiClient from './client';
import type {
  AuthResponse,
  LoginRequest,
  RegisterRequest,
  User,
} from '../types/auth.types';

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
