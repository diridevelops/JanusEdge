import {
  TickMarkType,
  type Time,
} from 'lightweight-charts';

type DateFormatStyle = 'year' | 'month' | 'day' | 'time' | 'timeWithSeconds' | 'tooltip';

export interface BacktestTimeFormatters {
  timeFormatter: (time: Time | number) => string;
  tickMarkFormatter: (
    time: Time | number,
    tickMarkType: TickMarkType,
    locale?: string
  ) => string | null;
}

function toEpochMilliseconds(time: Time | number): number | null {
  if (typeof time === 'number') {
    const timeMs = time * 1_000;
    return Number.isFinite(timeMs) ? timeMs : null;
  }

  if (typeof time === 'string') {
    const match = time.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return null;
    const [, year, month, day] = match;
    if (!year || !month || !day) return null;
    return Date.UTC(Number(year), Number(month) - 1, Number(day));
  }

  return Date.UTC(time.year, time.month - 1, time.day);
}

function getDateFormatOptions(style: DateFormatStyle): Intl.DateTimeFormatOptions {
  switch (style) {
    case 'year':
      return { year: 'numeric' };
    case 'month':
      return { month: 'short' };
    case 'day':
      return { day: '2-digit', month: 'short' };
    case 'time':
      return { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
    case 'timeWithSeconds':
      return { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' };
    case 'tooltip':
      return {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hourCycle: 'h23',
        timeZoneName: 'short',
      };
  }
}

/** Format chart time labels in the run's IANA timezone without shifting UTC data. */
export function createBacktestTimeFormatters(
  timezone: string,
  blindMode = false
): BacktestTimeFormatters {
  let displayTimezone = timezone.trim() || 'UTC';
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: displayTimezone });
  } catch {
    displayTimezone = 'UTC';
  }

  const formatterCache = new Map<string, Intl.DateTimeFormat>();
  const getFormatter = (locale: string | undefined, style: DateFormatStyle) => {
    const cacheKey = `${locale ?? ''}:${style}:${blindMode ? 'blind' : 'normal'}`;
    let formatter = formatterCache.get(cacheKey);
    if (!formatter) {
      formatter = new Intl.DateTimeFormat(locale || undefined, {
        timeZone: displayTimezone,
        ...(blindMode
          ? style === 'time' || style === 'timeWithSeconds'
            ? getDateFormatOptions(style)
            : {
              weekday: 'long',
              ...(style === 'tooltip'
                ? getDateFormatOptions('timeWithSeconds')
                : {}),
            }
          : getDateFormatOptions(style)),
      });
      formatterCache.set(cacheKey, formatter);
    }
    return formatter;
  };

  return {
    timeFormatter: (time) => {
      const timeMs = toEpochMilliseconds(time);
      if (timeMs === null) return String(time);
      const locale = typeof navigator === 'undefined' ? undefined : navigator.language;
      return getFormatter(locale, 'tooltip').format(new Date(timeMs));
    },
    tickMarkFormatter: (time, tickMarkType, locale) => {
      const timeMs = toEpochMilliseconds(time);
      if (timeMs === null) return null;

      const style: DateFormatStyle = tickMarkType === TickMarkType.Year
        ? 'year'
        : tickMarkType === TickMarkType.Month
          ? 'month'
          : tickMarkType === TickMarkType.DayOfMonth
            ? 'day'
            : tickMarkType === TickMarkType.TimeWithSeconds
              ? 'timeWithSeconds'
              : 'time';
      return getFormatter(locale, style).format(new Date(timeMs));
    },
  };
}
