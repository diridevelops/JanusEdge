import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import {
  calculateBacktestBracketSizing,
  createDefaultBacktestBracket,
  type BacktestBracketSizingInput,
} from './backtestBracketMath';
import {
  BacktestEntryPanel,
  shouldClearPriceDraft,
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
    onEntryTypeChange: vi.fn(),
    direction: 'long',
    onDirectionChange: vi.fn(),
    ...prices,
    onEntryPriceChange: vi.fn(),
    onStopLossPriceChange: vi.fn(),
    onTakeProfitPriceChange: vi.fn(),
    manualLots: null,
    onManualLotsChange: vi.fn(),
    ...overrides,
  };
}

describe('Backtest entry panel and bracket sizing', () => {
  it('keeps a typed price draft when its parent echoes that value and clears it for external price changes', () => {
    expect(shouldClearPriceDraft(1.23456, 1.23456)).toBe(false);
    expect(shouldClearPriceDraft(1.23456, 1.2346)).toBe(true);
    expect(shouldClearPriceDraft(null, 1.23456)).toBe(true);
  });

  it('defaults to an expanded panel with auto-size checked and all four entry choices', () => {
    const html = renderToStaticMarkup(<BacktestEntryPanel {...makePanelProps()} />);

    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('Market');
    expect(html).toContain('Limit');
    expect(html).toContain('Long');
    expect(html).toContain('Short');
    expect(html).toMatch(/<input type="checkbox" checked=""/);
    expect(html).toContain('Risk budget $100.00');
    expect(html).toContain('Quantity');
  });

  it('shows a place action before preview and a submit action only after preview is armed', () => {
    const callbacks = { onArmPreview: vi.fn(), onPlaceOrder: vi.fn(), onCancel: vi.fn() };
    const unarmedHtml = renderToStaticMarkup(
      <BacktestEntryPanel {...makePanelProps({ showActions: true, ...callbacks })} />
    );
    const armedHtml = renderToStaticMarkup(
      <BacktestEntryPanel {...makePanelProps({ showActions: true, previewActive: true, ...callbacks })} />
    );

    expect(unarmedHtml).toContain('>Place order</button>');
    expect(unarmedHtml).not.toContain('Cancel preview');
    expect(armedHtml).toContain('>Submit order</button>');
    expect(armedHtml).toContain('Cancel preview');
  });

  it('shows the current revealed close as a fixed market entry price', () => {
    const html = renderToStaticMarkup(
      <BacktestEntryPanel {...makePanelProps({ currentRevealedClose: 1.23456, entryPrice: 1.2 })} />
    );

    expect(html).toMatch(/<input[^>]*readOnly=""[^>]*value="1\.23456"/);
    expect(html).toContain('Fixed to the current revealed candle close.');
  });

  it('exposes limit price editing and the selected short direction accessibly', () => {
    const html = renderToStaticMarkup(
      <BacktestEntryPanel {...makePanelProps({ entryType: 'limit', direction: 'short', autoSize: false, manualLots: 0.25 })} />
    );

    expect(html).toMatch(/<button type="button" aria-pressed="true">Limit<\/button>/);
    expect(html).toMatch(/<button type="button" aria-pressed="true">Short<\/button>/);
    expect(html).toContain('Moves with the whole bracket when dragged on the chart.');
    expect(html).toContain('Manual lots');
    expect(html).toContain('value="0.25"');
    expect(html).not.toMatch(/<input type="checkbox" checked=""/);
  });

  it('can collapse the right-side panel without removing its accessible expand control', () => {
    const html = renderToStaticMarkup(<BacktestEntryPanel {...makePanelProps({ open: false })} />);

    expect(html).toContain('class="backtest-entry-panel is-collapsed"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-label="Expand entry panel"');
    expect(html).toContain('hidden=""');
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
});
