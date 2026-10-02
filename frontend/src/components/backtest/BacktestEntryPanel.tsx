import { useId, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
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

/** Step to the next valid lot-grid value using integer units to avoid float drift. */
export function stepManualLotsValue(
  currentLots: number | null,
  direction: -1 | 1,
  minimumLots = 0.001,
  lotIncrement = 0.001
): number | null {
  if (!Number.isFinite(minimumLots) || minimumLots <= 0
    || !Number.isFinite(lotIncrement) || lotIncrement <= 0) return null;
  if (currentLots == null) return direction > 0 ? minimumLots : null;
  if (!Number.isFinite(currentLots) || currentLots < minimumLots) return null;

  const decimals = Math.min(12, Math.max(
    minimumLots.toString().split('.')[1]?.length ?? 0,
    lotIncrement.toString().split('.')[1]?.length ?? 0,
    currentLots.toString().split('.')[1]?.length ?? 0,
  ));
  const scale = 10 ** decimals;
  const minUnits = Math.round(minimumLots * scale);
  const stepUnits = Math.round(lotIncrement * scale);
  if (stepUnits <= 0) return null;
  const stepsFromMinimum = (currentLots * scale - minUnits) / stepUnits;
  const wholeSteps = Math.floor(stepsFromMinimum);
  const nearestSteps = Math.round(stepsFromMinimum);
  const isOnGrid = Math.abs(stepsFromMinimum - nearestSteps) <= 1e-7;
  const nextSteps = direction > 0
    ? isOnGrid ? nearestSteps + 1 : wholeSteps + 1
    : isOnGrid ? nearestSteps - 1 : wholeSteps;
  const nextUnits = minUnits + nextSteps * stepUnits;
  return nextUnits >= minUnits ? Number((nextUnits / scale).toPrecision(14)) : null;
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
  const minimumLots = instrument.minLots ?? 0.001;
  const lotIncrement = instrument.lotIncrement ?? 0.001;
  const lotDecimals = Math.min(12, Math.max(
    minimumLots.toString().split('.')[1]?.length ?? 0,
    lotIncrement.toString().split('.')[1]?.length ?? 0,
  ));
  const nextManualLotsUp = stepManualLotsValue(manualLots, 1, minimumLots, lotIncrement);
  const nextManualLotsDown = stepManualLotsValue(manualLots, -1, minimumLots, lotIncrement);

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
            <div className="backtest-entry-panel-manual-size">
              <label htmlFor={`${panelId}-lots`}>Manual lots</label>
              <div className="backtest-entry-panel-lots-control">
                <input
                  id={`${panelId}-lots`}
                  type="number"
                  min={minimumLots}
                  step={lotIncrement}
                  inputMode="decimal"
                  value={manualLots ?? ''}
                  onChange={(event) => {
                    const value = event.currentTarget.value;
                    onManualLotsChange(value === '' ? null : Number(value));
                  }}
                />
                <div className="backtest-entry-panel-lots-stepper" role="group" aria-label="Adjust manual lots">
                  <button
                    type="button"
                    aria-label={`Increase manual lots by ${lotIncrement}`}
                    title={`Increase by ${lotIncrement} lots`}
                    disabled={nextManualLotsUp == null}
                    onClick={() => {
                      if (nextManualLotsUp != null) onManualLotsChange(nextManualLotsUp);
                    }}
                  >
                    <ChevronUp aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    aria-label={`Decrease manual lots by ${lotIncrement}`}
                    title={`Decrease by ${lotIncrement} lots`}
                    disabled={nextManualLotsDown == null}
                    onClick={() => {
                      if (nextManualLotsDown != null) onManualLotsChange(nextManualLotsDown);
                    }}
                  >
                    <ChevronDown aria-hidden="true" />
                  </button>
                </div>
              </div>
            </div>
          )}

          <dl className="backtest-entry-panel-metrics">
            <div><dt>Stop distance</dt><dd>{sizing.stopDistancePips == null ? '—' : `${sizing.stopDistancePips.toFixed(1)} ${instrument.priceUnitLabel ?? 'pips'}`}</dd></div>
            <div><dt>Quantity</dt><dd>{sizing.quantityLots == null ? '—' : `${sizing.quantityLots.toFixed(lotDecimals)} lots`}</dd></div>
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
