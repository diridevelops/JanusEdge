/** Paginated API response wrapper. */
export interface PaginatedResponse<T> {
  items: T[];
  trades?: T[];
  executions?: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

/** Standard API error shape. */
export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: unknown[];
  };
}

/** Common filter parameters shared across pages. */
export interface FilterParams {
  account?: string;
  symbol?: string;
  side?: string;
  tag?: string;
  date_from?: string;
  date_to?: string;
}
