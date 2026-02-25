import { Info } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
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
import { useChartColors } from '../../hooks/useChartColors';
import type { EvolutionPoint } from '../../types/analytics.types';
import type { FilterParams } from '../../types/common.types';
import { formatCurrency } from '../../utils/formatters';

interface EvolutionTabProps {
  filters: FilterParams;
}

interface InfoTooltipProps {
  text: string;
}

function InfoTooltip({ text }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  function openTooltip() {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (rect) {
      setPosition({
        top: rect.top - 8,
        left: rect.left + rect.width / 2,
      });
    }
    setOpen(true);
  }

  return (
    <span className="relative inline-flex">
      <button
        ref={buttonRef}
        type="button"
        className="inline-flex"
        onMouseEnter={openTooltip}
        onMouseLeave={() => setOpen(false)}
        onFocus={openTooltip}
        onBlur={() => setOpen(false)}
        aria-label="Chart info"
      >
        <Info className="h-4 w-4 text-gray-400" />
      </button>
      {open && (
        <div
          className="fixed z-[120] w-80 max-w-[80vw] px-3 py-2 text-xs text-gray-100 bg-gray-800 rounded-lg shadow-lg whitespace-pre-line pointer-events-none"
          style={{
            top: position.top,
            left: position.left,
            transform: 'translate(-50%, -100%)',
          }}
        >
          {text}
        </div>
      )}
    </span>
  );
}

/** Evolution tab with running metrics per trade index. */
export function EvolutionTab({ filters }: EvolutionTabProps) {
  const c = useChartColors();
  const [window, setWindow] = useState(50);
  const [halfLife, setHalfLife] = useState(35);
  const [points, setPoints] = useState<EvolutionPoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    getEvolution(filters, window, 2)
      .then(setPoints)
      .catch(() => {
        setPoints([]);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [filters, window]);

  const chartData = useMemo(() => {
    const alpha = 1 - Math.pow(2, -1 / halfLife);
    let ewmaRunningR: number | null = null;
    let ewmaRunningAppt: number | null = null;

    let runningPnlCount = 0;
    let runningPnlMean = 0;
    let runningPnlM2 = 0;

    const rollingPnlQueue: number[] = [];
    let rollingPnlSum = 0;
    let rollingPnlSumSq = 0;

    return points.map((point) => {
      const runningR = point.running_mean_r;
      if (runningR != null) {
        if (ewmaRunningR == null) {
          ewmaRunningR = runningR;
        } else {
          ewmaRunningR = alpha * runningR + (1 - alpha) * ewmaRunningR;
        }
      }

      rollingPnlQueue.push(point.net_pnl);
      rollingPnlSum += point.net_pnl;
      rollingPnlSumSq += point.net_pnl * point.net_pnl;
      if (rollingPnlQueue.length > window) {
        const removed = rollingPnlQueue.shift() ?? 0;
        rollingPnlSum -= removed;
        rollingPnlSumSq -= removed * removed;
      }
      const rollingAppt = rollingPnlSum / rollingPnlQueue.length;

      runningPnlCount += 1;
      const pnlDelta = point.net_pnl - runningPnlMean;
      runningPnlMean += pnlDelta / runningPnlCount;
      const pnlDelta2 = point.net_pnl - runningPnlMean;
      runningPnlM2 += pnlDelta * pnlDelta2;

      if (ewmaRunningAppt == null) {
        ewmaRunningAppt = runningPnlMean;
      } else {
        ewmaRunningAppt = (
          alpha * runningPnlMean
          + (1 - alpha) * ewmaRunningAppt
        );
      }

      let runningApptCiLow: number | null = null;
      let runningApptCiHigh: number | null = null;
      if (runningPnlCount > 1) {
        const runningVar = runningPnlM2 / (runningPnlCount - 1);
        const runningSe = Math.sqrt(runningVar) / Math.sqrt(runningPnlCount);
        runningApptCiLow = runningPnlMean - 1.96 * runningSe;
        runningApptCiHigh = runningPnlMean + 1.96 * runningSe;
      }

      let rollingApptCiLow: number | null = null;
      let rollingApptCiHigh: number | null = null;
      const rollingCount = rollingPnlQueue.length;
      if (rollingCount > 1) {
        const rollingVar = (
          rollingPnlSumSq
          - (rollingPnlSum * rollingPnlSum) / rollingCount
        ) / (rollingCount - 1);
        const safeRollingVar = Math.max(rollingVar, 0);
        const rollingSe = Math.sqrt(safeRollingVar) / Math.sqrt(rollingCount);
        rollingApptCiLow = rollingAppt - 1.96 * rollingSe;
        rollingApptCiHigh = rollingAppt + 1.96 * rollingSe;
      }

      return {
        ...point,
        x: point.trade_index,
        ewma_running_mean_r: ewmaRunningR,
        ewma_running_appt: ewmaRunningAppt,
        rolling_appt: rollingAppt,
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
        running_appt_ci_low: runningApptCiLow,
        running_appt_ci_high: runningApptCiHigh,
        running_appt_ci_range:
          runningApptCiLow != null && runningApptCiHigh != null
            ? runningApptCiHigh - runningApptCiLow
            : null,
        rolling_appt_ci_low: rollingApptCiLow,
        rolling_appt_ci_high: rollingApptCiHigh,
        rolling_appt_ci_range:
          rollingApptCiLow != null && rollingApptCiHigh != null
            ? rollingApptCiHigh - rollingApptCiLow
            : null,
      };
    });
  }, [points, window, halfLife]);

  const monthMarkers = useMemo(() => {
    const seenMonths = new Set<string>();
    return chartData
      .map((point) => {
        const source = point.exit_time ?? point.entry_time;
        if (!source) return null;
        const date = new Date(source);
        if (Number.isNaN(date.getTime())) return null;
        const monthKey = `${date.getUTCFullYear()}-${date.getUTCMonth()}`;
        if (seenMonths.has(monthKey)) return null;
        seenMonths.add(monthKey);
        const label = new Intl.DateTimeFormat('en-GB', {
          timeZone: 'UTC',
          day: 'numeric',
          month: 'short',
          year: '2-digit',
        }).format(
          new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1))
        );
        return {
          x: point.trade_index,
          label,
        };
      })
      .filter((item): item is { x: number; label: string } => item != null);
  }, [chartData]);

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

  const computeDomain = (values: Array<number | null | undefined>): [number, number] => {
    const numericValues = values.filter((value): value is number => value != null && Number.isFinite(value));
    if (numericValues.length === 0) {
      return [-1, 1];
    }
    let min = Math.min(...numericValues, 0);
    let max = Math.max(...numericValues, 0);
    if (min === max) {
      const delta = Math.abs(min) > 0 ? Math.abs(min) * 0.25 : 1;
      min -= delta;
      max += delta;
    }
    const pad = (max - min) * 0.12;
    return [min - pad, max + pad];
  };

  const computeTightDomain = (
    values: Array<number | null | undefined>
  ): [number, number] => {
    const numericValues = values
      .filter(
        (value): value is number =>
          value != null && Number.isFinite(value)
      )
      .sort((left, right) => left - right);

    if (numericValues.length === 0) {
      return [-1, 1];
    }

    const quantile = (
      sortedValues: number[],
      q: number
    ): number => {
      const pos = (sortedValues.length - 1) * q;
      const base = Math.floor(pos);
      const rest = pos - base;
      const baseValue = sortedValues[base] ?? 0;
      const nextValue = sortedValues[base + 1];
      if (nextValue !== undefined) {
        return (
          baseValue
          + rest * (nextValue - baseValue)
        );
      }
      return baseValue;
    };

    let min = Math.min(...numericValues, 0);
    let max = Math.max(...numericValues, 0);

    if (numericValues.length >= 20) {
      const p02 = quantile(numericValues, 0.02);
      const p98 = quantile(numericValues, 0.98);
      min = Math.min(p02, 0);
      max = Math.max(p98, 0);
    }

    if (min === max) {
      const delta = Math.abs(min) > 0 ? Math.abs(min) * 0.25 : 1;
      min -= delta;
      max += delta;
    }

    const pad = (max - min) * 0.08;
    return [min - pad, max + pad];
  };

  const alignDomainToZeroRatio = (
    referenceDomain: [number, number],
    values: Array<number | null | undefined>
  ): [number, number] => {
    const numericValues = values.filter(
      (value): value is number => value != null && Number.isFinite(value)
    );
    if (numericValues.length === 0) {
      return [-1, 1];
    }

    const [refMin, refMax] = referenceDomain;
    const refRange = refMax - refMin;
    if (refRange <= 0) {
      return computeDomain(numericValues);
    }

    let zeroRatio = (-refMin) / refRange;
    zeroRatio = Math.min(0.99, Math.max(0.01, zeroRatio));

    const requiredUp = Math.max(0, ...numericValues);
    const requiredDown = Math.max(0, ...numericValues.map((value) => -value));

    const upWeight = 1 - zeroRatio;
    const downWeight = zeroRatio;
    const scale = Math.max(
      requiredUp / upWeight,
      requiredDown / downWeight,
      1
    );

    const alignedMax = scale * upWeight;
    const alignedMin = -scale * downWeight;

    if (alignedMin === alignedMax) {
      return [alignedMin - 1, alignedMax + 1];
    }

    return [alignedMin, alignedMax];
  };

  const formatR = (value: number): string => {
    return parseFloat(value.toFixed(3)).toString();
  };

  const runningLeftDomain = computeTightDomain(
    chartData.map((point) => point.running_mean_r)
  );
  const rollingLeftDomain = computeDomain(
    chartData.map((point) => point.rolling_mean_r)
  );
  const cumulativeLeftDomain = computeDomain(
    chartData.map((point) => point.cum_r)
  );
  const runningRightAlignedDomain = alignDomainToZeroRatio(
    runningLeftDomain,
    chartData.map((point) => point.appt_running)
  );
  const rollingRightAlignedDomain = alignDomainToZeroRatio(
    rollingLeftDomain,
    chartData.map((point) => point.rolling_appt)
  );
  const cumulativeRightAlignedDomain = alignDomainToZeroRatio(
    cumulativeLeftDomain,
    chartData.map((point) => point.cum_net_pnl)
  );

  if (isLoading) {
    return (
      <div className="h-64 flex items-center justify-center bg-gray-50 dark:bg-gray-800 rounded-lg animate-pulse">
        <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">
        No evolution data
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label htmlFor="evolution-window" className="text-sm text-gray-600 dark:text-gray-400">
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

        <label htmlFor="evolution-halflife" className="text-sm text-gray-600 dark:text-gray-400 ml-3">
          EWMA half-life
        </label>
        <select
          id="evolution-halflife"
          className="input-field w-28"
          value={halfLife}
          onChange={(e) => setHalfLife(parseInt(e.target.value, 10))}
        >
          <option value={25}>25</option>
          <option value={35}>35</option>
          <option value={50}>50</option>
        </select>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Running Mean R (95% CI) vs Running APPT</h3>
            <InfoTooltip
              text={
                'What this shows: Running mean R (left axis) with 95% CI = average risk-normalized edge per trade; Running APPT (right axis) = average profit per trade in money. Undefined R trades are excluded from R statistics.\n\nHow to read:\n• Mean R above 0 with CI mostly above 0: evidence of positive edge.\n• APPT > 0 but Mean R ≤ 0: profits driven by position sizing/exposure rather than edge.\n• EWMA above Mean: recent improvement; EWMA below Mean: recent deterioration.\n• EWMA crossing 0 before Mean: early regime shift signal.\n• CI narrows as trades grow: increasing statistical stability.'
              }
            />
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 34 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={c.grid} />
              <XAxis dataKey="x" tick={{ fontSize: 11, fill: c.tick }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11, fill: c.tick }} domain={runningLeftDomain} tickFormatter={formatR} allowDataOverflow />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 11, fill: c.tick }}
                tickFormatter={(v: number) => formatCurrency(v)}
                domain={runningRightAlignedDomain}
                allowDataOverflow
              />
              <Tooltip
                formatter={(value, name, payload) => {
                  const numeric = toNumberOrNull(value);
                  if (name === 'running_mean_r') return [numeric?.toFixed(3) ?? '—', 'Running mean R'];
                  if (name === 'ewma_running_mean_r') return [numeric?.toFixed(3) ?? '—', 'EWMA (Running mean R)'];
                  if (name === 'appt_running') return [formatCurrency(numeric ?? 0), 'Running APPT'];
                  if (name === 'ewma_running_appt') return [formatCurrency(numeric ?? 0), 'EWMA (Running APPT)'];
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
              <ReferenceLine yAxisId="left" y={0} stroke="#9ca3af" strokeDasharray="3 3" />
              <ReferenceLine yAxisId="right" y={0} stroke="#9ca3af" strokeDasharray="3 3" />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="running_mean_r_ci_low"
                stackId="running_ci"
                stroke="none"
                fill="transparent"
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="running_ci_range"
                stackId="running_ci"
                stroke="none"
                fill="#93c5fd"
                fillOpacity={0.35}
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
              <Area
                yAxisId="right"
                type="monotone"
                dataKey="running_appt_ci_low"
                stackId="running_appt_ci"
                stroke="none"
                fill="transparent"
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
              <Area
                yAxisId="right"
                type="monotone"
                dataKey="running_appt_ci_range"
                stackId="running_appt_ci"
                stroke="none"
                fill="#fdba74"
                fillOpacity={0.25}
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="running_mean_r"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="ewma_running_mean_r"
                stroke="#0f766e"
                strokeWidth={1.75}
                strokeDasharray="5 4"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                yAxisId="right"
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
                dataKey="ewma_running_appt"
                stroke="#c2410c"
                strokeWidth={1.75}
                strokeDasharray="5 4"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="included_r_count"
                stroke="transparent"
                dot={false}
                isAnimationActive={false}
                tooltipType="none"
              />
              {monthMarkers.map((marker) => (
                <ReferenceLine
                  key={`running-${marker.x}`}
                  x={marker.x}
                  yAxisId="left"
                  stroke={c.grid}
                  strokeDasharray="2 4"
                  ifOverflow="extendDomain"
                  label={{ value: marker.label, position: 'insideBottom', fill: c.tick, fontSize: 10 }}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Rolling Expectancy R (95% CI) vs Rolling APPT</h3>
            <InfoTooltip
              text={
                'What this shows: Rolling (windowed) expectancy in R (left axis) with 95% CI and Rolling APPT (right axis), over the last W trades (selected window). Captures recent regime performance.\n\nHow to read:\n• R rolling mean > 0: current edge is positive; < 0 indicates deterioration.\n• APPT diverges from R: money results driven by sizing/fees/execution, not edge.\n• Wide CI or frequent zero-crossings: limited data or unstable recent performance; consider larger W or more trades.'
              }
            />
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 34 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={c.grid} />
              <XAxis dataKey="x" tick={{ fontSize: 11, fill: c.tick }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11, fill: c.tick }} domain={rollingLeftDomain} tickFormatter={formatR} allowDataOverflow />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 11, fill: c.tick }}
                tickFormatter={(v: number) => formatCurrency(v)}
                domain={rollingRightAlignedDomain}
                allowDataOverflow
              />
              <Tooltip
                formatter={(value, name, payload) => {
                  const numeric = toNumberOrNull(value);
                  if (name === 'rolling_mean_r') return [numeric?.toFixed(3) ?? '—', 'Rolling mean R'];
                  if (name === 'rolling_appt') return [formatCurrency(numeric ?? 0), 'Rolling APPT'];
                  if (name === 'rolling_mean_r_ci_low') return [numeric?.toFixed(3) ?? '—', 'CI low'];
                  if (name === 'rolling_mean_r_ci_high') return [numeric?.toFixed(3) ?? '—', 'CI high'];
                  if (name === 'rolling_r_count') {
                    const total = payload?.payload?.trade_index ?? 0;
                    return [`${numeric ?? 0} of ${total}`, 'Included trades'];
                  }
                  if (name === 'rolling_pl_ratio_trade') {
                    const stable = payload?.payload?.rolling_pl_ratio_stable;
                    if (!stable) {
                      return ['—', 'P/L Ratio (Trade)'];
                    }
                    return [numeric?.toFixed(2) ?? '—', 'P/L Ratio (Trade)'];
                  }
                  return [numeric ?? '—', name];
                }}
                labelFormatter={(label) => `Trade #${label}`}
              />
              <ReferenceLine yAxisId="left" y={0} stroke="#9ca3af" strokeDasharray="3 3" />
              <ReferenceLine yAxisId="right" y={0} stroke="#9ca3af" strokeDasharray="3 3" />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="rolling_mean_r_ci_low"
                stackId="rolling_ci"
                stroke="none"
                fill="transparent"
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="rolling_ci_range"
                stackId="rolling_ci"
                stroke="none"
                fill="#86efac"
                fillOpacity={0.3}
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
              <Area
                yAxisId="right"
                type="monotone"
                dataKey="rolling_appt_ci_low"
                stackId="rolling_appt_ci"
                stroke="none"
                fill="transparent"
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
              <Area
                yAxisId="right"
                type="monotone"
                dataKey="rolling_appt_ci_range"
                stackId="rolling_appt_ci"
                stroke="none"
                fill="#fdba74"
                fillOpacity={0.2}
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="rolling_mean_r"
                stroke="#16a34a"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="rolling_appt"
                stroke="#f97316"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="rolling_pl_ratio_trade"
                stroke="transparent"
                dot={false}
                isAnimationActive={false}
                tooltipType="none"
              />
              {monthMarkers.map((marker) => (
                <ReferenceLine
                  key={`rolling-${marker.x}`}
                  x={marker.x}
                  yAxisId="left"
                  stroke={c.grid}
                  strokeDasharray="2 4"
                  ifOverflow="extendDomain"
                  label={{ value: marker.label, position: 'insideBottom', fill: c.tick, fontSize: 10 }}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Cumulative R vs Cumulative Net P&L</h3>
            <InfoTooltip
              text={
                'What this shows: Total performance over time in two currencies: Cumulative R (left axis, dimensionless) and Cumulative Net P&L (right axis, currency). R excludes trades with undefined initial risk; P&L is net of fees.\n\nHow to read:\n• Both lines rising: healthy, scalable performance.\n• Cum$ ↑ while CumR flat/↓: profits mainly from exposure/sizing, not risk-normalized edge.\n• Drawdowns/flat spots: reveal path dependence and risk of the system.'
              }
            />
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 34 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={c.grid} />
              <XAxis dataKey="x" tick={{ fontSize: 11, fill: c.tick }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11, fill: c.tick }} domain={cumulativeLeftDomain} tickFormatter={formatR} allowDataOverflow />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 11, fill: c.tick }}
                tickFormatter={(v: number) => formatCurrency(v)}
                domain={cumulativeRightAlignedDomain}
                allowDataOverflow
              />
              <Tooltip
                formatter={(value: number, name: string) => {
                  if (name === 'cum_r') return [formatR(value), 'Cumulative R'];
                  if (name === 'cum_net_pnl') return [formatCurrency(value), 'Cumulative Net P&L'];
                  return [value, name];
                }}
                labelFormatter={(label) => `Trade #${label}`}
              />
              <ReferenceLine yAxisId="left" y={0} stroke="#9ca3af" strokeDasharray="3 3" />
              <ReferenceLine yAxisId="right" y={0} stroke="#9ca3af" strokeDasharray="3 3" />
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
              {monthMarkers.map((marker) => (
                <ReferenceLine
                  key={`cum-${marker.x}`}
                  x={marker.x}
                  yAxisId="left"
                  stroke={c.grid}
                  strokeDasharray="2 4"
                  ifOverflow="extendDomain"
                  label={{ value: marker.label, position: 'insideBottom', fill: c.tick, fontSize: 10 }}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
