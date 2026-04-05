import type { AuthResponse } from '../types/auth.types';

type AuthEventHandlers = {
  onAuthResponse?: (response: AuthResponse) => void;
  onUnauthorized?: () => void;
};

let accessToken: string | null = null;
let handlers: AuthEventHandlers = {};

/** Return the current in-memory access token. */
export function getAccessToken(): string | null {
  return accessToken;
}

/** Replace the current in-memory access token. */
export function setAccessToken(token: string | null): void {
  accessToken = token;
}

/** Clear the current in-memory access token. */
export function clearAccessToken(): void {
  accessToken = null;
}

/** Register global auth lifecycle handlers. */
export function registerAuthEventHandlers(
  nextHandlers: AuthEventHandlers
): () => void {
  handlers = nextHandlers;
  return () => {
    handlers = {};
  };
}

/** Notify the app that auth has been restored or refreshed. */
export function notifyAuthResponse(
  response: AuthResponse
): void {
  handlers.onAuthResponse?.(response);
}

/** Notify the app that auth is no longer valid. */
export function notifyUnauthorized(): void {
  handlers.onUnauthorized?.();
}
