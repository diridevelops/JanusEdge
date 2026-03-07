/**
 * Stop-analysis worker.
 *
 * Computes BCa bootstrap confidence intervals for overshoot metrics
 * off the main thread to keep the UI responsive.
 */

export interface StopAnalysisWorkerInput {
  overshoots: number[];
  bootstrapSamples: number;
}

export interface StopAnalysisCI {
  lower: number;
  upper: number;
}

export interface StopAnalysisWorkerOutput {
  mean: StopAnalysisCI;
  median: StopAnalysisCI;
  p75: StopAnalysisCI;
  p90: StopAnalysisCI;
  p95: StopAnalysisCI;
  iqr: StopAnalysisCI;
}

type MetricKey = keyof StopAnalysisWorkerOutput;

const CONFIDENCE = 0.95;
const DEGENERACY_EPSILON = 1e-12;
const ADJUSTMENT_DENOMINATOR_EPSILON = 1e-12;
const TIE_EPSILON = 1e-12;

function sortNumbers(values: number[]): number[] {
  return [...values].sort((left, right) => left - right);
}

function quantileSorted(sortedValues: number[], probability: number): number {
  if (sortedValues.length === 0) return 0;
  if (sortedValues.length === 1) return sortedValues[0]!;

  const rank = probability * (sortedValues.length - 1);
  const lowIndex = Math.floor(rank);
  const highIndex = Math.min(lowIndex + 1, sortedValues.length - 1);
  const weight = rank - lowIndex;
  const lowValue = sortedValues[lowIndex]!;
  const highValue = sortedValues[highIndex]!;
  return lowValue + ((highValue - lowValue) * weight);
}

function summarize(values: number[]): Record<MetricKey, number> {
  const sorted = sortNumbers(values);
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const median = quantileSorted(sorted, 0.5);
  const p75 = quantileSorted(sorted, 0.75);
  const p90 = quantileSorted(sorted, 0.9);
  const p95 = quantileSorted(sorted, 0.95);
  const p25 = quantileSorted(sorted, 0.25);

  return {
    mean,
    median,
    p75,
    p90,
    p95,
    iqr: p75 - p25,
  };
}

function clampProbability(probability: number): number {
  const epsilon = 1e-10;
  return Math.min(1 - epsilon, Math.max(epsilon, probability));
}

function normalCdf(value: number): number {
  const absValue = Math.abs(value);
  const t = 1 / (1 + 0.2316419 * absValue);
  const d = 0.3989423 * Math.exp((-value * value) / 2);
  let probability = d * t * (
    0.3193815 +
    t * (
      -0.3565638 +
      t * (
        1.781478 +
        t * (
          -1.821256 +
          t * 1.330274
        )
      )
    )
  );
  probability = 1 - probability;
  return value < 0 ? 1 - probability : probability;
}

function normalQuantile(probability: number): number {
  const p = clampProbability(probability);
  const a = [
    -3.969683028665376e+01,
    2.209460984245205e+02,
    -2.759285104469687e+02,
    1.38357751867269e+02,
    -3.066479806614716e+01,
    2.506628277459239e+00,
  ] as const;
  const b = [
    -5.447609879822406e+01,
    1.615858368580409e+02,
    -1.556989798598866e+02,
    6.680131188771972e+01,
    -1.328068155288572e+01,
  ] as const;
  const c = [
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e+00,
    -2.549732539343734e+00,
    4.374664141464968e+00,
    2.938163982698783e+00,
  ] as const;
  const d = [
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e+00,
    3.754408661907416e+00,
  ] as const;

  const low = 0.02425;
  const high = 1 - low;

  if (p < low) {
    const q = Math.sqrt(-2 * Math.log(p));
    const numerator = (((((c[0] * q) + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5];
    const denominator = ((((d[0] * q) + d[1]) * q + d[2]) * q + d[3]) * q + 1;
    return numerator / denominator;
  }

  if (p > high) {
    const q = Math.sqrt(-2 * Math.log(1 - p));
    const numerator = (((((c[0] * q) + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5];
    const denominator = ((((d[0] * q) + d[1]) * q + d[2]) * q + d[3]) * q + 1;
    return -(numerator / denominator);
  }

  const q = p - 0.5;
  const r = q * q;
  const numerator = (((((a[0] * r) + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5];
  const denominator = (((((b[0] * r) + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1;
  return (numerator * q) / denominator;
}

function percentileFromSorted(sortedValues: number[], probability: number): number {
  return quantileSorted(sortedValues, clampProbability(probability));
}

function valuesAreNearlyEqual(left: number, right: number): boolean {
  const scale = Math.max(1, Math.abs(left), Math.abs(right));
  return Math.abs(left - right) <= (TIE_EPSILON * scale);
}

function computeBiasCorrectionProbability(bootstrapStats: number[], thetaHat: number): number {
  let lessCount = 0;
  let equalCount = 0;

  for (const value of bootstrapStats) {
    if (valuesAreNearlyEqual(value, thetaHat)) {
      equalCount += 1;
    } else if (value < thetaHat) {
      lessCount += 1;
    }
  }

  return clampProbability((lessCount + (0.5 * equalCount)) / bootstrapStats.length);
}

function adjustedBcaProbability(z0: number, zAlpha: number, acceleration: number): number {
  const numerator = z0 + zAlpha;
  const denominator = 1 - (acceleration * (z0 + zAlpha));

  if (Math.abs(denominator) < ADJUSTMENT_DENOMINATOR_EPSILON) {
    if (Math.abs(numerator) < ADJUSTMENT_DENOMINATOR_EPSILON) {
      return normalCdf(z0);
    }

    return numerator * denominator > 0 ? 1 : 0;
  }

  return normalCdf(z0 + (numerator / denominator));
}

function bcaInterval(
  values: number[],
  metricKey: MetricKey,
  bootstrapSamples: number,
): StopAnalysisCI {
  if (values.length === 0) {
    return { lower: 0, upper: 0 };
  }

  const thetaHat = summarize(values)[metricKey];
  if (values.length < 2) {
    return { lower: thetaHat, upper: thetaHat };
  }

  const bootstrapStats: number[] = [];
  for (let sampleIndex = 0; sampleIndex < bootstrapSamples; sampleIndex += 1) {
    const sample: number[] = [];
    for (let valueIndex = 0; valueIndex < values.length; valueIndex += 1) {
      sample.push(values[Math.floor(Math.random() * values.length)]!);
    }
    bootstrapStats.push(summarize(sample)[metricKey]);
  }

  const sortedBootstrap = sortNumbers(bootstrapStats);
  if ((sortedBootstrap[sortedBootstrap.length - 1]! - sortedBootstrap[0]!) < DEGENERACY_EPSILON) {
    return { lower: sortedBootstrap[0]!, upper: sortedBootstrap[0]! };
  }

  const z0 = normalQuantile(computeBiasCorrectionProbability(bootstrapStats, thetaHat));

  const jackknifeStats: number[] = [];
  for (let index = 0; index < values.length; index += 1) {
    const jackknifeSample = values.filter((_, valueIndex) => valueIndex !== index);
    if (jackknifeSample.length === 0) {
      jackknifeStats.push(thetaHat);
    } else {
      jackknifeStats.push(summarize(jackknifeSample)[metricKey]);
    }
  }

  const jackknifeMean = jackknifeStats.reduce((sum, value) => sum + value, 0) / jackknifeStats.length;
  const centered = jackknifeStats.map((value) => jackknifeMean - value);
  const numerator = centered.reduce((sum, value) => sum + (value ** 3), 0);
  const denominatorBase = centered.reduce((sum, value) => sum + (value ** 2), 0);
  const denominator = 6 * (denominatorBase ** 1.5);
  const acceleration = denominator === 0 ? 0 : numerator / denominator;

  const alphaLow = (1 - CONFIDENCE) / 2;
  const alphaHigh = 1 - alphaLow;
  const zLow = normalQuantile(alphaLow);
  const zHigh = normalQuantile(alphaHigh);

  const adjustedLow = adjustedBcaProbability(z0, zLow, acceleration);
  const adjustedHigh = adjustedBcaProbability(z0, zHigh, acceleration);

  const lower = percentileFromSorted(sortedBootstrap, adjustedLow);
  const upper = percentileFromSorted(sortedBootstrap, adjustedHigh);

  return lower <= upper
    ? { lower, upper }
    : { lower: upper, upper: lower };
}

self.onmessage = (event: MessageEvent<StopAnalysisWorkerInput>) => {
  const { overshoots, bootstrapSamples } = event.data;
  const metrics: MetricKey[] = ['mean', 'median', 'p75', 'p90', 'p95', 'iqr'];
  const output = {} as StopAnalysisWorkerOutput;

  for (const metricKey of metrics) {
    output[metricKey] = bcaInterval(overshoots, metricKey, bootstrapSamples);
  }

  self.postMessage(output);
};