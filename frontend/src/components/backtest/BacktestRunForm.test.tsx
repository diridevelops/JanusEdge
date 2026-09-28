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
};

describe('Backtest run period selection form', () => {
  it('keeps the manual creation request shape unchanged', () => {
    expect(buildCreateBacktestRunRequest(baseValues, 'Europe/Rome')).toEqual({
      instrument: 'EUR-USD',
      start_date: '2026-01-05',
      end_date: '2026-01-06',
      display_timezone: 'Europe/Rome',
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
});
