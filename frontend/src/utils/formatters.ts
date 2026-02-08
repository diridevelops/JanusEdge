/**
 * Format a number as USD currency.
 *
 * @param value - The number to format.
 * @returns Formatted currency string (e.g., "$1,234.56").
 */
export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value);
}

/**
 * Format a number with sign prefix and color class.
 *
 * @param value - The P&L value.
 * @returns Object with formatted text and CSS class.
 */
export function formatPnL(value: number): {
  text: string;
  className: string;
} {
  const formatted = formatCurrency(Math.abs(value));
  if (value > 0) {
    return { text: `+${formatted}`, className: 'pnl-positive' };
  }
  if (value < 0) {
    return { text: `-${formatted}`, className: 'pnl-negative' };
  }
  return { text: formatted, className: 'text-gray-500' };
}

/**
 * Format a percentage value.
 *
 * @param value - The percentage (e.g., 65.5).
 * @param decimals - Number of decimal places.
 * @returns Formatted string (e.g., "65.50%").
 */
export function formatPercent(
  value: number,
  decimals = 2
): string {
  return `${value.toFixed(decimals)}%`;
}

/**
 * Format seconds into a human-readable duration.
 *
 * @param seconds - Duration in seconds.
 * @returns Human-readable string (e.g., "2h 15m").
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const mins = Math.floor(seconds / 60);
  if (mins < 60) {
    return `${mins}m`;
  }
  const hrs = Math.floor(mins / 60);
  const remainingMins = mins % 60;
  if (hrs < 24) {
    return remainingMins > 0 ? `${hrs}h ${remainingMins}m` : `${hrs}h`;
  }
  const days = Math.floor(hrs / 24);
  const remainingHrs = hrs % 24;
  return remainingHrs > 0 ? `${days}d ${remainingHrs}h` : `${days}d`;
}

/**
 * Format an ISO date string for display.
 *
 * @param isoString - ISO 8601 date string.
 * @returns Formatted date string (e.g., "Jan 15, 2025 10:30 AM").
 */
export function formatDateTime(
  isoString: string,
  timezone?: string
): string {
  const opts: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  };
  if (timezone) {
    opts.timeZone = timezone;
  }
  return new Date(isoString).toLocaleString('en-US', opts);
}

/**
 * Format an ISO date string as date only.
 *
 * @param isoString - ISO 8601 date string.
 * @returns Formatted date (e.g., "Jan 15, 2025").
 */
export function formatDate(
  isoString: string,
  timezone?: string
): string {
  const opts: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  };
  if (timezone) {
    opts.timeZone = timezone;
  }
  return new Date(isoString).toLocaleDateString('en-US', opts);
}

/**
 * Format a number with specified decimal places.
 *
 * @param value - The number to format.
 * @param decimals - Decimal places (default 2).
 * @returns Formatted number string.
 */
export function formatNumber(
  value: number,
  decimals = 2
): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}
