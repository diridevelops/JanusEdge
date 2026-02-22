import apiClient from './client';
import type {
  AnalyticsSummary,
  EquityCurvePoint,
  DrawdownPoint,
  CalendarDay,
  DistributionBucket,
  TimeOfDayEntry,
  TagAnalytics,
  ApptByDayOfWeekEntry,
  ApptByTimeframeEntry,
  EvolutionPoint,
} from '../types/analytics.types';
import type { FilterParams } from '../types/common.types';

/** Get summary metrics. */
export async function getSummary(
  filters?: FilterParams
): Promise<AnalyticsSummary> {
  const res = await apiClient.get<AnalyticsSummary>(
    '/analytics/summary',
    { params: filters }
  );
  return res.data;
}

/** Get equity curve data. */
export async function getEquityCurve(
  filters?: FilterParams
): Promise<EquityCurvePoint[]> {
  const res = await apiClient.get<EquityCurvePoint[]>(
    '/analytics/equity-curve',
    { params: filters }
  );
  return res.data;
}

/** Get drawdown series. */
export async function getDrawdown(
  filters?: FilterParams
): Promise<DrawdownPoint[]> {
  const res = await apiClient.get<DrawdownPoint[]>(
    '/analytics/drawdown',
    { params: filters }
  );
  return res.data;
}

/** Get calendar heatmap data. */
export async function getCalendar(
  filters?: FilterParams
): Promise<CalendarDay[]> {
  const res = await apiClient.get<CalendarDay[]>(
    '/analytics/calendar',
    { params: filters }
  );
  return res.data;
}

/** Get P&L distribution. */
export async function getDistribution(
  filters?: FilterParams,
  bucketSize?: number
): Promise<DistributionBucket[]> {
  const res = await apiClient.get<DistributionBucket[]>(
    '/analytics/distribution',
    { params: { ...filters, bucket_size: bucketSize } }
  );
  return res.data;
}

/** Get time-of-day analysis. */
export async function getTimeOfDay(
  filters?: FilterParams
): Promise<TimeOfDayEntry[]> {
  const res = await apiClient.get<TimeOfDayEntry[]>(
    '/analytics/time-of-day',
    { params: filters }
  );
  return res.data;
}

/** Get metrics grouped by tag. */
export async function getByTag(
  filters?: FilterParams
): Promise<TagAnalytics[]> {
  const res = await apiClient.get<TagAnalytics[]>(
    '/analytics/by-tag',
    { params: filters }
  );
  return res.data;
}

/** Get APPT grouped by day of week. */
export async function getApptByDayOfWeek(
  filters?: FilterParams,
  timezone?: string
): Promise<ApptByDayOfWeekEntry[]> {
  const res = await apiClient.get<ApptByDayOfWeekEntry[]>(
    '/analytics/appt-by-day-of-week',
    { params: { ...filters, timezone } }
  );
  return res.data;
}

/** Get APPT grouped by 15-minute entry timeframe. */
export async function getApptByTimeframe(
  filters?: FilterParams,
  timezone?: string
): Promise<ApptByTimeframeEntry[]> {
  const res = await apiClient.get<ApptByTimeframeEntry[]>(
    '/analytics/appt-by-timeframe',
    { params: { ...filters, timezone } }
  );
  return res.data;
}

/** Get running/rolling trade evolution metrics. */
export async function getEvolution(
  filters?: FilterParams,
  window: number = 50,
  minSideCount: number = 5
): Promise<EvolutionPoint[]> {
  const res = await apiClient.get<EvolutionPoint[]>(
    '/analytics/evolution',
    {
      params: {
        ...filters,
        window,
        min_side_count: minSideCount,
      },
    }
  );
  return res.data;
}
