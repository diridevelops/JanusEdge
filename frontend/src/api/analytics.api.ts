import apiClient from './client';
import type {
  AnalyticsSummary,
  EquityCurvePoint,
  DrawdownPoint,
  CalendarDay,
  DistributionBucket,
  TimeOfDayEntry,
  TagAnalytics,
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
