import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  BacktestRunForm,
  type BacktestRunFormValues,
} from './BacktestRunForm';
import { buildCreateBacktestRunRequest } from '../../utils/backtestRunRequest';

const baseValues: BacktestRunFormValues = {
  instrument: 'EUR-USD',
  startDate: '2026-01-05',
  endDate: '2026-01-06',
  periodSelection: 'manual',
  periodMonths: 1,
  blindMode: false,
  initialBalanceUsd: 10_000,
  riskPercent: 1,
  totalSpreadPips: 0,
  slippagePips: 0,
  commissionUsdPerLotPerSide: 0,
};

const defaultExecutionCosts = {
  total_spread_pips: 0,
  slippage_pips: 0,
  commission_usd_per_lot_per_side: 0,
};

describe('Backtest run period selection form', () => {
  it('sends balance and risk with a manual run request', () => {
    expect(buildCreateBacktestRunRequest(baseValues, 'Europe/Rome')).toEqual({
      instrument: 'EUR-USD',
      start_date: '2026-01-05',
      end_date: '2026-01-06',
      display_timezone: 'Europe/Rome',
      initial_balance_usd: 10_000,
      risk_percent: 1,
      execution_costs: defaultExecutionCosts,
    });
  });

  it('sends the selected random duration without manual date fields', () => {
    expect(buildCreateBacktestRunRequest({
      ...baseValues,
      periodSelection: 'random',
      periodMonths: 6,
    }, 'Europe/Rome')).toEqual({
      instrument: 'EUR-USD',
      display_timezone: 'Europe/Rome',
      period_selection: 'random',
      period_months: 6,
      initial_balance_usd: 10_000,
      risk_percent: 1,
      execution_costs: defaultExecutionCosts,
    });
  });

  it('preserves manual and random request shapes when Blind mode is off', () => {
    expect(buildCreateBacktestRunRequest({
      ...baseValues,
      blindMode: false,
    }, 'Europe/Rome')).toEqual({
      instrument: 'EUR-USD',
      start_date: '2026-01-05',
      end_date: '2026-01-06',
      display_timezone: 'Europe/Rome',
      initial_balance_usd: 10_000,
      risk_percent: 1,
      execution_costs: defaultExecutionCosts,
    });
    expect(buildCreateBacktestRunRequest({
      ...baseValues,
      periodSelection: 'random',
      periodMonths: 6,
      blindMode: false,
    }, 'Europe/Rome')).toEqual({
      instrument: 'EUR-USD',
      display_timezone: 'Europe/Rome',
      period_selection: 'random',
      period_months: 6,
      initial_balance_usd: 10_000,
      risk_percent: 1,
      execution_costs: defaultExecutionCosts,
    });
  });

  it('marks blind requests and carries the selected random duration only', () => {
    expect(buildCreateBacktestRunRequest({
      ...baseValues,
      periodSelection: 'random',
      periodMonths: 3,
      blindMode: true,
    }, 'Europe/Rome')).toEqual({
      instrument: 'EUR-USD',
      display_timezone: 'Europe/Rome',
      period_selection: 'random',
      period_months: 3,
      blind_mode: true,
      initial_balance_usd: 10_000,
      risk_percent: 1,
      execution_costs: defaultExecutionCosts,
    });
  });

  it('forces random period selection in the request helper when Blind mode is enabled', () => {
    expect(buildCreateBacktestRunRequest({
      ...baseValues,
      periodSelection: 'manual',
      blindMode: true,
    }, 'Europe/Rome')).toEqual({
      instrument: 'EUR-USD',
      display_timezone: 'Europe/Rome',
      period_selection: 'random',
      period_months: 1,
      blind_mode: true,
      initial_balance_usd: 10_000,
      risk_percent: 1,
      execution_costs: defaultExecutionCosts,
    });
  });

  it('offers random durations and disables both date controls in random mode', () => {
    const randomValues = { ...baseValues, periodSelection: 'random' as const };
    const html = renderToStaticMarkup(
      <BacktestRunForm
        displayTimezone="Europe/Rome"
        initialValues={randomValues}
        onCancel={() => undefined}
        onCreated={() => undefined}
      />
    );

    expect(html).toContain('Random period');
    expect(html).toContain('1 month');
    expect(html).toContain('3 months');
    expect(html).toContain('6 months');
    expect(html).toContain('12 months');
    expect(html).toMatch(/id="backtest-start-date"[^>]*disabled=""/);
    expect(html).toMatch(/id="backtest-end-date"[^>]*disabled=""/);
  });

  it('leaves the manual date controls enabled when manual dates are selected', () => {
    const html = renderToStaticMarkup(
      <BacktestRunForm
        displayTimezone="UTC"
        initialValues={baseValues}
        onCancel={() => undefined}
        onCreated={() => undefined}
      />
    );

    expect(html).toMatch(/id="backtest-start-date"[^>]*value="2026-01-05"/);
    expect(html).toMatch(/id="backtest-end-date"[^>]*value="2026-01-06"/);
    expect(html).not.toMatch(/id="backtest-start-date"[^>]*disabled=""/);
    expect(html).not.toMatch(/id="backtest-end-date"[^>]*disabled=""/);
  });

  it('renders Blind mode unchecked by default and exposes random mode as the forced selection', () => {
    const html = renderToStaticMarkup(
      <BacktestRunForm
        displayTimezone="UTC"
        initialValues={baseValues}
        onCancel={() => undefined}
        onCreated={() => undefined}
      />
    );

    const blindCheckbox = html.match(/<input type="checkbox"[^>]*>/)?.[0];
    expect(blindCheckbox).toBeDefined();
    expect(blindCheckbox).not.toContain('checked=""');
    expect(html).toContain('<option value="manual" selected="">Choose dates</option>');
    expect(html).not.toMatch(/id="backtest-period-selection"[^>]*disabled=""/);
  });

  it('renders blind mode with random selection locked and manual dates suppressed', () => {
    const html = renderToStaticMarkup(
      <BacktestRunForm
        displayTimezone="UTC"
        initialValues={{ ...baseValues, blindMode: true, periodSelection: 'manual' }}
        onCancel={() => undefined}
        onCreated={() => undefined}
      />
    );

    const blindCheckbox = html.match(/<input type="checkbox"[^>]*>/)?.[0];
    expect(blindCheckbox).toContain('checked=""');
    expect(html).toMatch(/id="backtest-period-selection"[^>]*disabled=""/);
    expect(html).toContain('<option value="random" selected="">Random period</option>');
    expect(html).toMatch(/id="backtest-start-date"[^>]*disabled=""/);
    expect(html).toMatch(/id="backtest-end-date"[^>]*disabled=""/);
    expect(html).toContain('Random period');
  });

  it('keeps the period selector editable when Blind mode is explicitly off', () => {
    const html = renderToStaticMarkup(
      <BacktestRunForm
        displayTimezone="UTC"
        initialValues={{ ...baseValues, blindMode: false, periodSelection: 'random' }}
        onCancel={() => undefined}
        onCreated={() => undefined}
      />
    );

    expect(html).toContain('<option value="random" selected="">Random period</option>');
    expect(html).not.toMatch(/id="backtest-period-selection"[^>]*disabled=""/);
  });

  it('sends custom balance and risk for random runs', () => {
    expect(buildCreateBacktestRunRequest({
      ...baseValues,
      periodSelection: 'random',
      initialBalanceUsd: 50_000,
      riskPercent: 1.75,
      totalSpreadPips: 1.2,
      slippagePips: 0.4,
      commissionUsdPerLotPerSide: 2.5,
    }, 'Europe/Rome')).toEqual({
      instrument: 'EUR-USD',
      display_timezone: 'Europe/Rome',
      period_selection: 'random',
      period_months: 1,
      initial_balance_usd: 50_000,
      risk_percent: 1.75,
      execution_costs: {
        total_spread_pips: 1.2,
        slippage_pips: 0.4,
        commission_usd_per_lot_per_side: 2.5,
      },
    });
  });

  it('defaults balance and risk to USD 10,000 and 1 percent and exposes settings', () => {
    const html = renderToStaticMarkup(
      <BacktestRunForm
        displayTimezone="UTC"
        initialValues={baseValues}
        onCancel={() => undefined}
        onCreated={() => undefined}
      />
    );

    expect(html).toMatch(/id="backtest-initial-balance"[^>]*value="10000"/);
    expect(html).toMatch(/id="backtest-risk-percent"[^>]*value="1"/);
    expect(html).toMatch(/id="backtest-cost-spread"[^>]*value="0"/);
    expect(html).toMatch(/id="backtest-cost-slippage"[^>]*value="0"/);
    expect(html).toMatch(/id="backtest-cost-commission"[^>]*value="0"/);
    expect(html).toContain('Initial balance (USD)');
    expect(html).toContain('Risk per entry (%)');
  });
});
