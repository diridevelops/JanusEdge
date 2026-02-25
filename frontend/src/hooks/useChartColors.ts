import { useMemo } from 'react';
import { useTheme } from './useTheme';

/** Shared color tokens for Recharts and TradingView charts in light/dark mode. */
export interface ChartColors {
  /** CartesianGrid stroke color. */
  grid: string;
  /** XAxis / YAxis tick text fill. */
  tick: string;
  /** Tooltip background colour. */
  tooltipBg: string;
  /** Tooltip border colour. */
  tooltipBorder: string;
  /** Tooltip text colour. */
  tooltipText: string;
  /** ReferenceLine stroke colour. */
  reference: string;
  /** Axis line colour (XAxis axisLine, etc.). */
  axisLine: string;
  /** Whether dark mode is active. */
  isDark: boolean;
}

const LIGHT: Omit<ChartColors, 'isDark'> = {
  grid: '#f3f4f6',       // gray-100
  tick: '#6b7280',       // gray-500
  tooltipBg: '#ffffff',
  tooltipBorder: '#e5e7eb', // gray-200
  tooltipText: '#111827',   // gray-900
  reference: '#9ca3af',     // gray-400
  axisLine: '#e5e7eb',
};

const DARK: Omit<ChartColors, 'isDark'> = {
  grid: '#374151',       // gray-700
  tick: '#9ca3af',       // gray-400
  tooltipBg: '#1f2937',  // gray-800
  tooltipBorder: '#4b5563', // gray-600
  tooltipText: '#f3f4f6',   // gray-100
  reference: '#6b7280',     // gray-500
  axisLine: '#4b5563',
};

/**
 * Returns theme-aware colour tokens for chart components.
 *
 * Usage:
 * ```tsx
 * const c = useChartColors();
 * <CartesianGrid stroke={c.grid} />
 * <XAxis tick={{ fontSize: 11, fill: c.tick }} />
 * ```
 */
export function useChartColors(): ChartColors {
  const { isDark } = useTheme();
  return useMemo(() => ({ ...(isDark ? DARK : LIGHT), isDark }), [isDark]);
}
