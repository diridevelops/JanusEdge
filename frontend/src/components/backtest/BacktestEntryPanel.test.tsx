import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import {
  calculateBacktestBracketSizing,
  createDefaultBacktestBracket,
  type BacktestBracketSizingInput,
} from './backtestBracketMath';
import {
  BacktestEntryPanel,
  stepManualLotsValue,
  type BacktestEntryPanelProps,
} from './BacktestEntryPanel';

const instrument = {
  pipSize: 0.0001,
  pricePrecision: 5,
  contractSize: 100_000,
  quoteCurrency: 'USD',
  quoteToUsdRate: null,
};

const account = { currentBalanceUsd: 10_000, riskPercent: 1 };
const prices = { entryPrice: 1.1, stopLossPrice: 1.099, takeProfitPrice: 1.101 };

function makePanelProps(overrides: Partial<BacktestEntryPanelProps> = {}): BacktestEntryPanelProps {
  return {
    instrument,
    account,
    costs: { totalSpreadPips: 0, slippagePips: 0, commissionUsdPerLotPerSide: 0 },
    currentRevealedClose: 1.1,
    entryType: 'market',
    direction: 'long',
    onOrderSelectionChange: vi.fn(),
    ...prices,
    manualLots: null,
    onManualLotsChange: vi.fn(),
    ...overrides,
  };
}

describe('Backtest entry panel and bracket sizing', () => {
  it('defaults to a compact header, four non-toggle order choices, and auto-size', () => {
    const html = renderToStaticMarkup(<BacktestEntryPanel {...makePanelProps()} />);

    expect(html).toMatch(/<header class="backtest-entry-panel-header"><h2[^>]*>Entry order<\/h2><\/header>/);
    expect(html).toMatch(/>\s*Sell Market\s*<\/button>/);
    expect(html).toMatch(/>\s*Buy Market\s*<\/button>/);
    expect(html).toMatch(/>\s*Buy Limit\s*<\/button>/);
    expect(html).toMatch(/>\s*Sell Limit\s*<\/button>/);
    expect(html).not.toContain('aria-pressed=');
    expect(html).not.toContain('Simulation');
    expect(html).not.toContain('Collapse entry panel');
    expect(html).toMatch(/<input type="checkbox" checked=""/);
    expect(html).toContain('Risk budget $100.00');
    expect(html).toContain('Quantity');
  });

  it('keeps submit and cancel controls off the entry panel', () => {
    const html = renderToStaticMarkup(<BacktestEntryPanel {...makePanelProps()} />);

    expect(html).not.toContain('Place order');
    expect(html).not.toContain('Submit');
    expect(html).not.toContain('Cancel preview');
  });

  it('keeps all four combined order choices accessible without price fields or guidance text', () => {
    const html = renderToStaticMarkup(
      <BacktestEntryPanel {...makePanelProps({ entryType: 'limit', direction: 'short', autoSize: false, manualLots: 0.25 })} />
    );

    expect(html).toMatch(/>\s*Buy Market\s*<\/button>/);
    expect(html).toMatch(/>\s*Sell Market\s*<\/button>/);
    expect(html).toMatch(/>\s*Buy Limit\s*<\/button>/);
    expect(html).toMatch(/>\s*Sell Limit\s*<\/button>/);
    expect(html).not.toContain('aria-pressed=');
    expect(html).not.toContain('Entry price');
    expect(html).not.toContain('Stop-loss');
    expect(html).not.toContain('Take-profit');
    expect(html).not.toContain('Set entry, stop-loss');
    expect(html).not.toMatch(/<input[^>]*type="text"/);
    expect(html).toContain('Manual lots');
    expect(html).toContain('value="0.25"');
    expect(html).not.toMatch(/<input type="checkbox" checked=""/);
  });

  it('steps manual lots by exactly 0.01 while retaining thousandth precision', () => {
    expect(stepManualLotsValue(0.01, 1)).toBe(0.02);
    expect(stepManualLotsValue(0.02, -1)).toBe(0.01);
    expect(stepManualLotsValue(0.015, 1)).toBe(0.025);
    expect(stepManualLotsValue(0.015, -1)).toBe(0.005);
    expect(stepManualLotsValue(0.001, 1)).toBe(0.011);
    expect(stepManualLotsValue(null, 1)).toBe(0.01);
    expect(stepManualLotsValue(null, -1)).toBeNull();
    expect(stepManualLotsValue(0.01, -1)).toBeNull();
  });

  it('renders attached manual-lots step buttons with the minimum boundary disabled', () => {
    const html = renderToStaticMarkup(
      <BacktestEntryPanel {...makePanelProps({ autoSize: false, manualLots: 0.01 })} />
    );

    expect(html).toMatch(/id="backtest-entry-panel-[^"]+-lots" type="number" min="0\.001" step="any"/);
    expect(html).toContain('aria-label="Adjust manual lots"');
    expect(html).toContain('aria-label="Increase manual lots by 0.01"');
    expect(html).toContain('aria-label="Decrease manual lots by 0.01" title="Decrease by 0.01 lots" disabled=""');
  });

  it('does not render a collapsible control in the entry header', () => {
    const html = renderToStaticMarkup(<BacktestEntryPanel {...makePanelProps()} />);
    const header = html.match(/<header class="backtest-entry-panel-header">([\s\S]*?)<\/header>/)?.[1] ?? '';

    expect(header).toContain('Entry order');
    expect(header).not.toContain('<button');
    expect(header).not.toContain('SIMULATION');
  });

  it('derives the initial stop from USD risk and sets an equal-distance 1R target', () => {
    const bracket = createDefaultBacktestBracket({
      entryPrice: 1.1,
      direction: 'long',
      instrument,
      account,
    });

    expect(bracket).toMatchObject({
      entryPrice: 1.1,
      stopLossPrice: 1.099,
      takeProfitPrice: 1.101,
      stopDistancePips: 10,
    });
    expect(Math.abs(bracket.entryPrice! - bracket.stopLossPrice!))
      .toBeCloseTo(Math.abs(bracket.takeProfitPrice! - bracket.entryPrice!));
  });

  it('reverses the default protection levels for a short bracket', () => {
    const bracket = createDefaultBacktestBracket({
      entryPrice: 1.1,
      direction: 'short',
      instrument,
      account,
    });

    expect(bracket.stopLossPrice).toBeGreaterThan(bracket.entryPrice!);
    expect(bracket.takeProfitPrice).toBeLessThan(bracket.entryPrice!);
    expect(Math.abs(bracket.entryPrice! - bracket.stopLossPrice!))
      .toBeCloseTo(Math.abs(bracket.takeProfitPrice! - bracket.entryPrice!));
  });

  it('uses the as-of USD-per-quote rate and includes spread, slippage, and both commissions in auto-size', () => {
    const input: BacktestBracketSizingInput = {
      entryType: 'limit',
      direction: 'long',
      entryPrice: 150,
      stopLossPrice: 149.99,
      takeProfitPrice: 150.01,
      instrument: {
        pipSize: 0.01,
        pricePrecision: 3,
        contractSize: 100_000,
        quoteCurrency: 'JPY',
        quoteToUsdRate: 0.0067,
      },
      account,
      costs: { totalSpreadPips: 0.4, slippagePips: 0.1, commissionUsdPerLotPerSide: 1 },
      autoSize: true,
      manualLots: null,
    };
    const sizing = calculateBacktestBracketSizing(input);

    expect(sizing.usdPipValuePerStandardLot).toBeCloseTo(6.7);
    expect(sizing.quantityLots).toBe(7.861);
    expect(sizing.projectedRiskUsd).toBeLessThanOrEqual(sizing.riskBudgetUsd!);
    expect(sizing.canPlaceOrder).toBe(true);
  });

  it('blocks auto-size when the 0.001-lot minimum exceeds the configured risk budget', () => {
    const input: BacktestBracketSizingInput = {
      entryType: 'market',
      direction: 'long',
      entryPrice: 1.1,
      stopLossPrice: 1.099,
      takeProfitPrice: 1.101,
      instrument,
      account: { currentBalanceUsd: 0.5, riskPercent: 1 },
      autoSize: true,
      manualLots: null,
    };
    const sizing = calculateBacktestBracketSizing(input);

    expect(sizing.quantityLots).toBeNull();
    expect(sizing.canPlaceOrder).toBe(false);
    expect(sizing.errors).toContain('The minimum size of 0.001 lots would exceed the USD risk budget.');
  });

  it('keeps a projected risk summary in manual mode and still includes modeled costs', () => {
    const html = renderToStaticMarkup(
      <BacktestEntryPanel
        {...makePanelProps({
          autoSize: false,
          manualLots: 0.25,
          costs: { totalSpreadPips: 1, slippagePips: 0.1, commissionUsdPerLotPerSide: 2 },
        })}
      />
    );

    expect(html).toContain('Projected risk');
    expect(html).toContain('$29.00');
    expect(html).toContain('Projected risk and reward include modeled spread, slippage, and round-trip commission.');
  });

  it('continues to accept typed manual lots at 0.001 increments', () => {
    const sizing = calculateBacktestBracketSizing({
      entryType: 'market',
      direction: 'long',
      entryPrice: 1.1,
      stopLossPrice: 1.099,
      takeProfitPrice: 1.101,
      instrument,
      account,
      autoSize: false,
      manualLots: 0.001,
    });

    expect(sizing.quantityLots).toBe(0.001);
    expect(sizing.canPlaceOrder).toBe(true);
  });
});
