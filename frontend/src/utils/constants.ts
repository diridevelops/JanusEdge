/** Application-wide constants. */

export const APP_NAME = 'Janus Edge';
export const APP_SLUG = 'janusedge';
export const APP_TAGLINE = 'Past insight. Future performance.';
export const BACKUP_FILENAME = `${APP_SLUG}-backup.zip`;

/** Available timezones for registration. */
export const TIMEZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Phoenix',
  'America/Anchorage',
  'Pacific/Honolulu',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Paris',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Kolkata',
  'Australia/Sydney',
  'UTC',
] as const;

/** Default pagination size. */
export const DEFAULT_PAGE_SIZE = 25;

/** Chart interval options. */
export const CHART_INTERVALS = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1h' },
  { value: '1d', label: '1D' },
] as const;
