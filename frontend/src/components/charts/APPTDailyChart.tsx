import {
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    ReferenceLine,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';
import type { EquityCurvePoint } from '../../types/analytics.types';
import { formatCurrency } from '../../utils/formatters';

function getNiceIntegerStep(range: number, targetTickCount = 6): number {
  const safeRange = Math.max(range, 1);
  const roughStep = safeRange / Math.max(targetTickCount - 1, 1);
  const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep)));
  const residual = roughStep / magnitude;

  if (residual <= 1) return Math.max(1, 1 * magnitude);
  if (residual <= 2) return Math.max(1, 2 * magnitude);
  if (residual <= 5) return Math.max(1, 5 * magnitude);
  return Math.max(1, 10 * magnitude);
}

interface APPTDailyChartProps {
  data: EquityCurvePoint[];
  isLoading: boolean;
}

/** Daily APPT (Average Profitability Per Trade) histogram. */
export function APPTDailyChart({ data, isLoading }: APPTDailyChartProps) {
  if (isLoading) {
    return (
      <div className="h-64 flex items-center justify-center bg-gray-50 rounded-lg animate-pulse">
        <div className="h-4 w-32 bg-gray-200 rounded" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
        No APPT data
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString(),
  }));

  const apptValues = chartData.map((point) => point.appt);
  const rawMin = Math.min(...apptValues, 0);
  const rawMax = Math.max(...apptValues, 0);
  const step = getNiceIntegerStep(rawMax - rawMin);
  let yMin = Math.floor(rawMin / step) * step;
  let yMax = Math.ceil(rawMax / step) * step;

  if (yMin === yMax) {
    yMin -= step;
    yMax += step;
  }

  const yTicks: number[] = [];
  for (let value = yMin; value <= yMax; value += step) {
    yTicks.push(value);
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
        <XAxis dataKey="displayDate" tick={{ fontSize: 11 }} />
        <YAxis
          tick={{ fontSize: 11 }}
          domain={[yMin, yMax]}
          ticks={yTicks}
          allowDecimals={false}
          tickFormatter={(v: number) => formatCurrency(v)}
        />
        <Tooltip
          formatter={(value: number) => [formatCurrency(value), 'APPT']}
          labelStyle={{ fontWeight: 600 }}
        />
        <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
        <Bar
          dataKey="appt"
          name="appt"
          barSize={12}
          isAnimationActive={false}
        >
          {chartData.map((entry) => (
            <Cell
              key={entry.date}
              fill={entry.appt >= 0 ? '#22c55e' : '#ef4444'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
