import { useId, useState } from 'react';
import {
  calculateBacktestBracketSizing,
  type BacktestBracketPrices,
  type BacktestEntryCosts,
  type BacktestEntryInstrument,
  type BacktestEntryType,
  type BacktestRiskAccount,
  type BacktestTradeDirection,
} from './backtestBracketMath';

export interface BacktestEntryPanelProps extends BacktestBracketPrices {
  instrument: BacktestEntryInstrument;
  account: BacktestRiskAccount;
  costs?: BacktestEntryCosts;
  /** The revealed close anchors market-order sizing and preview placement. */
  currentRevealedClose: number;
  entryType: BacktestEntryType;
  direction: BacktestTradeDirection;
  onOrderSelectionChange: (entryType: BacktestEntryType, direction: BacktestTradeDirection) => void;
  /** Omit autoSize to use the component's default-on local setting. */
  autoSize?: boolean;
  onAutoSizeChange?: (enabled: boolean) => void;
  manualLots: number | null;
  onManualLotsChange: (lots: number | null) => void;
}

function formatUsd(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value);
}

export function BacktestEntryPanel({
  instrument,
  account,
  costs,
  currentRevealedClose,
  entryType,
  direction,
  onOrderSelectionChange,
  entryPrice,
  stopLossPrice,
  takeProfitPrice,
  autoSize,
  onAutoSizeChange,
  manualLots,
  onManualLotsChange,
}: BacktestEntryPanelProps) {
  const generatedId = useId();
  const panelId = `backtest-entry-panel-${generatedId.replace(/:/g, '')}`;
  const [localAutoSize, setLocalAutoSize] = useState(true);
  const useAutoSize = autoSize ?? localAutoSize;

  const sizingInput = {
    entryType,
    direction,
    entryPrice: entryType === 'market' ? currentRevealedClose : entryPrice,
    stopLossPrice,
    takeProfitPrice,
    instrument,
    account,
    costs,
    autoSize: useAutoSize,
    manualLots,
  } as const;
  const sizing = calculateBacktestBracketSizing(sizingInput);
  const errorText = sizing.errors[0];
  const projectedOverBudget = sizing.projectedRiskPercent != null && sizing.projectedRiskPercent > 100;
  const initialBudget = Number.isFinite(account.currentBalanceUsd) && Number.isFinite(account.riskPercent)
    ? account.currentBalanceUsd * account.riskPercent / 100
    : null;

  function setAutoSize(next: boolean) {
    if (autoSize == null) setLocalAutoSize(next);
    onAutoSizeChange?.(next);
  }

  return (
    <aside
      className="backtest-entry-panel"
      aria-label="Simulated entry order"
      data-testid="backtest-entry-panel"
    >
      <header className="backtest-entry-panel-header">
        <h2 id={`${panelId}-heading`}>Entry order</h2>
      </header>

      <div id={`${panelId}-body`} className="backtest-entry-panel-body" aria-labelledby={`${panelId}-heading`}>
        <div className="backtest-entry-panel-order-options" role="group" aria-label="Order side and type">
          <button
            type="button"
            className="backtest-entry-panel-order-option"
            data-side="buy"
            onClick={() => onOrderSelectionChange('market', 'long')}
          >
            Buy Market
          </button>
          <button
            type="button"
            className="backtest-entry-panel-order-option"
            data-side="sell"
            onClick={() => onOrderSelectionChange('market', 'short')}
          >
            Sell Market
          </button>
          <button
            type="button"
            className="backtest-entry-panel-order-option"
            data-side="buy"
            onClick={() => onOrderSelectionChange('limit', 'long')}
          >
            Buy Limit
          </button>
          <button
            type="button"
            className="backtest-entry-panel-order-option"
            data-side="sell"
            onClick={() => onOrderSelectionChange('limit', 'short')}
          >
            Sell Limit
          </button>
        </div>

        <section className="backtest-entry-panel-sizing" aria-label="Quantity and projected risk">
          <div className="backtest-entry-panel-sizing-heading">
            <h3>Position size</h3>
            <span>Risk budget {formatUsd(initialBudget)}</span>
          </div>
          <label className="backtest-entry-panel-auto-size">
            <input type="checkbox" checked={useAutoSize} onChange={(event) => setAutoSize(event.currentTarget.checked)} />
            <span>Auto-size from risk budget</span>
          </label>

          {!useAutoSize && (
            <label className="backtest-entry-panel-manual-size" htmlFor={`${panelId}-lots`}>
              Manual lots
              <input
                id={`${panelId}-lots`}
                type="number"
                min="0.001"
                step="0.001"
                inputMode="decimal"
                value={manualLots ?? ''}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  onManualLotsChange(value === '' ? null : Number(value));
                }}
              />
            </label>
          )}

          <dl className="backtest-entry-panel-metrics">
            <div><dt>Stop distance</dt><dd>{sizing.stopDistancePips == null ? '—' : `${sizing.stopDistancePips.toFixed(1)} pips`}</dd></div>
            <div><dt>Quantity</dt><dd>{sizing.quantityLots == null ? '—' : `${sizing.quantityLots.toFixed(3)} lots`}</dd></div>
            <div><dt>Projected risk</dt><dd>{formatUsd(sizing.projectedRiskUsd)}</dd></div>
            <div><dt>Target reward</dt><dd>{formatUsd(sizing.projectedRewardUsd)}</dd></div>
            <div><dt>Risk / reward</dt><dd>{sizing.riskRewardRatio == null ? '—' : sizing.riskRewardRatio.toFixed(2)}</dd></div>
          </dl>
          {projectedOverBudget && !useAutoSize && (
            <p className="backtest-entry-panel-warning" role="status">
              Projected risk is {sizing.projectedRiskPercent?.toFixed(1)}% of the configured USD risk budget.
            </p>
          )}
          {errorText && <p className="backtest-entry-panel-error" role="status">{errorText}</p>}
          <p className="backtest-entry-panel-cost-note">Projected risk and reward include modeled spread, slippage, and round-trip commission.</p>
        </section>

      </div>
    </aside>
  );
}

export default BacktestEntryPanel;
