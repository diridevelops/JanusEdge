/** User profile returned by the API. */
export interface User {
  id: string;
  username: string;
  timezone: string;
  display_timezone: string;
  starting_equity: number;
  created_at: string;
}

/** Login request payload. */
export interface LoginRequest {
  username: string;
  password: string;
}

/** Register request payload. */
export interface RegisterRequest {
  username: string;
  password: string;
  timezone: string;
}

/** Auth response from login/register. */
export interface AuthResponse {
  token: string;
  user: User;
}
