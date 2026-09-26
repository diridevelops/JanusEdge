const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Parse an HTML date-input value as a calendar date, independent of local time. */
function parseCalendarDate(value: string): Date | null {
  const match = ISO_DATE_PATTERN.exec(value);
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(0);
  parsed.setUTCHours(0, 0, 0, 0);
  parsed.setUTCFullYear(year, month - 1, day);

  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) {
    return null;
  }

  return parsed;
}

function formatCalendarDate(date: Date): string {
  const year = String(date.getUTCFullYear()).padStart(4, '0');
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Return the last inclusive end date before the start date's one-year
 * anniversary. JavaScript's year increment rolls February 29 to March 1 in
 * the following year, making February 28 the final permitted date.
 */
export function getLatestAllowedBacktestEndDate(
  startDate: string
): string | null {
  const start = parseCalendarDate(startDate);
  if (!start || start.getUTCFullYear() >= 9999) return null;

  const anniversary = new Date(start);
  anniversary.setUTCFullYear(start.getUTCFullYear() + 1);
  anniversary.setUTCDate(anniversary.getUTCDate() - 1);
  return formatCalendarDate(anniversary);
}

/**
 * Validate an inclusive date range using calendar dates, not the browser's
 * local timezone. The end must be before the start's one-year anniversary.
 */
export function isValidBacktestDateRange(
  startDate: string,
  endDate: string
): boolean {
  const start = parseCalendarDate(startDate);
  const end = parseCalendarDate(endDate);
  const latestEndDate = getLatestAllowedBacktestEndDate(startDate);

  return Boolean(
    start
    && end
    && latestEndDate
    && end.getTime() >= start.getTime()
    && endDate <= latestEndDate
  );
}

/** Return a user-facing validation message, or null when the range is valid. */
export function getBacktestDateRangeError(
  startDate: string,
  endDate: string
): string | null {
  if (!startDate || !endDate) return 'Select both a start date and an end date.';
  if (!parseCalendarDate(startDate) || !parseCalendarDate(endDate)) {
    return 'Enter valid calendar dates.';
  }

  if (endDate < startDate) {
    return 'The end date must be on or after the start date.';
  }

  const latestEndDate = getLatestAllowedBacktestEndDate(startDate);
  if (!latestEndDate || endDate > latestEndDate) {
    return `The maximum range is one year. Choose an end date on or before ${latestEndDate ?? 'the one-year limit'}.`;
  }

  return null;
}
