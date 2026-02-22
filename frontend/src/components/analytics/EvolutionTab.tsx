import { useEffect, useMemo, useState } from 'react';
import {
    Area,
    CartesianGrid,
    ComposedChart,
    Line,
    ReferenceLine,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';
import { getEvolution } from '../../api/analytics.api';
import type { EvolutionPoint } from '../../types/analytics.types';
import type { FilterParams } from '../../types/common.types';
import { formatCurrency } from '../../utils/formatters';

interface EvolutionTabProps {
  filters: FilterParams;
}

/** Evolution tab with running metrics per trade index. */
export function EvolutionTab({ filters }: EvolutionTabProps) {
  const [window, setWindow] = useState(50);
  const [points, setPoints] = useState<EvolutionPoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    getEvolution(filters, window, 5)
      .then(setPoints)
      .catch(() => {
        setPoints([]);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [filters, window]);

  const chartData = useMemo(() => {
    return points.map((point) => ({
      ...point,
      x: point.trade_index,
      running_ci_range:
        point.running_mean_r_ci_low != null
        && point.running_mean_r_ci_high != null
          ? point.running_mean_r_ci_high - point.running_mean_r_ci_low
          : null,
      rolling_ci_range:
        point.rolling_mean_r_ci_low != null
        && point.rolling_mean_r_ci_high != null
          ? point.rolling_mean_r_ci_high - point.rolling_mean_r_ci_low
          : null,
    }));
  }, [points]);

  const toNumberOrNull = (value: unknown): number | null => {
    if (typeof value === 'number') {
      return value;
    }
    if (typeof value === 'string') {
      const parsed = parseFloat(value);
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  };

  if (isLoading) {
    return (
      <div className="h-64 flex items-center justify-center bg-gray-50 rounded-lg animate-pulse">
        <div className="h-4 w-32 bg-gray-200 rounded" />
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
        No evolution data
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label htmlFor="evolution-window" className="text-sm text-gray-600">
          Rolling window
        </label>
        <select
          id="evolution-window"
          className="input-field w-28"
          value={window}
          onChange={(e) => setWindow(parseInt(e.target.value, 10))}
        >
          <option value={30}>30</option>
          <option value={50}>50</option>
          <option value={100}>100</option>
        </select>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Running Mean R (95% CI)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="x" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value, name, payload) => {
                  const numeric = toNumberOrNull(value);
                  if (name === 'running_mean_r') return [numeric?.toFixed(3) ?? '—', 'Running mean R'];
                  if (name === 'running_mean_r_ci_low') return [numeric?.toFixed(3) ?? '—', 'CI low'];
                  if (name === 'running_mean_r_ci_high') return [numeric?.toFixed(3) ?? '—', 'CI high'];
                  if (name === 'included_r_count') {
                    const total = payload?.payload?.trade_index ?? 0;
                    return [`${numeric ?? 0} of ${total}`, 'Included trades'];
                  }
                  return [numeric ?? '—', name];
                }}
                labelFormatter={(label) => `Trade #${label}`}
              />
              <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
              <Area
                type="monotone"
                dataKey="running_mean_r_ci_low"
                stackId="running_ci"
                stroke="none"
                fill="transparent"
                isAnimationActive={false}
                connectNulls
              />
              <Area
                type="monotone"
                dataKey="running_ci_range"
                stackId="running_ci"
                stroke="none"
                fill="#93c5fd"
                fillOpacity={0.35}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="running_mean_r"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="included_r_count"
                stroke="transparent"
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Rolling Expectancy R (95% CI)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="x" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value, name, payload) => {
                  const numeric = toNumberOrNull(value);
                  if (name === 'rolling_mean_r') return [numeric?.toFixed(3) ?? '—', 'Rolling mean R'];
                  if (name === 'rolling_mean_r_ci_low') return [numeric?.toFixed(3) ?? '—', 'CI low'];
                  if (name === 'rolling_mean_r_ci_high') return [numeric?.toFixed(3) ?? '—', 'CI high'];
                  if (name === 'rolling_r_count') {
                    const total = payload?.payload?.trade_index ?? 0;
                    return [`${numeric ?? 0} of ${total}`, 'Included trades'];
                  }
                  return [numeric ?? '—', name];
                }}
                labelFormatter={(label) => `Trade #${label}`}
              />
              <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
              <Area
                type="monotone"
                dataKey="rolling_mean_r_ci_low"
                stackId="rolling_ci"
                stroke="none"
                fill="transparent"
                isAnimationActive={false}
                connectNulls
              />
              <Area
                type="monotone"
                dataKey="rolling_ci_range"
                stackId="rolling_ci"
                stroke="none"
                fill="#86efac"
                fillOpacity={0.3}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="rolling_mean_r"
                stroke="#16a34a"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Cumulative R vs Cumulative Net P&L</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="x" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) => formatCurrency(v)}
              />
              <Tooltip
                formatter={(value: number, name: string) => {
                  if (name === 'cum_r') return [value.toFixed(2), 'Cumulative R'];
                  if (name === 'cum_net_pnl') return [formatCurrency(value), 'Cumulative Net P&L'];
                  return [value, name];
                }}
                labelFormatter={(label) => `Trade #${label}`}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="cum_r"
                stroke="#7c3aed"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="cum_net_pnl"
                stroke="#0ea5e9"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">APPT & Rolling P/L Ratio (Trade)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="x" tick={{ fontSize: 11 }} />
              <YAxis
                yAxisId="left"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) => formatCurrency(v)}
              />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value, name, payload) => {
                  const numeric = toNumberOrNull(value);
                  if (name === 'appt_running') return [formatCurrency(numeric ?? 0), 'Running APPT'];
                  if (name === 'rolling_pl_ratio_trade') {
                    const stable = payload?.payload?.rolling_pl_ratio_stable;
                    if (!stable) {
                      return ['—', 'P/L Ratio (Trade)'];
                    }
                    return [numeric?.toFixed(2) ?? '—', 'P/L Ratio (Trade)'];
                  }
                  if (name === 'rolling_window_wins') {
                    return [numeric ?? 0, 'Window wins'];
                  }
                  if (name === 'rolling_window_losses') {
                    return [numeric ?? 0, 'Window losses'];
                  }
                  return [numeric ?? '—', name];
                }}
                labelFormatter={(label) => `Trade #${label}`}
              />
              <ReferenceLine yAxisId="right" y={1} stroke="#a3a3a3" strokeDasharray="3 3" />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="appt_running"
                stroke="#f97316"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="rolling_pl_ratio_trade"
                stroke="#111827"
                strokeWidth={2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="rolling_window_wins"
                stroke="transparent"
                dot={false}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="rolling_window_losses"
                stroke="transparent"
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="mt-2 text-xs text-gray-500">
            P/L Ratio is hidden until window has at least 5 winners and 5 losers.
          </p>
        </div>
      </div>
    </div>
  );
}
