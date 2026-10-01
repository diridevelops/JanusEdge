import { useEffect, useId, useRef, useState, type ChangeEvent } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import {
  calculateBacktestBracketSizing,
  createBacktestEntryOrderDraft,
  type BacktestBracketPrices,
  type BacktestEntryCosts,
  type BacktestEntryInstrument,
  type BacktestEntryOrderDraft,
  type BacktestEntryType,
  type BacktestRiskAccount,
  type BacktestTradeDirection,
} from './backtestBracketMath';

export interface BacktestEntryPanelProps extends BacktestBracketPrices {
  instrument: BacktestEntryInstrument;
  account: BacktestRiskAccount;
  costs?: BacktestEntryCosts;
  /** The revealed close anchors a new market preview and is displayed read-only. */
  currentRevealedClose: number;
  entryType: BacktestEntryType;
  onEntryTypeChange: (entryType: BacktestEntryType) => void;
  direction: BacktestTradeDirection;
  onDirectionChange: (direction: BacktestTradeDirection) => void;
  onEntryPriceChange: (price: number) => void;
  onStopLossPriceChange: (price: number) => void;
  onTakeProfitPriceChange: (price: number) => void;
  /** Omit autoSize to use the component's default-on local setting. */
  autoSize?: boolean;
  onAutoSizeChange?: (enabled: boolean) => void;
  manualLots: number | null;
  onManualLotsChange: (lots: number | null) => void;
  /** Omit open to use the component's initially expanded local state. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  showActions?: boolean;
  /** Whether the chart bracket is currently armed for review and submission. */
  previewActive?: boolean;
  orderDisabled?: boolean;
  orderPending?: boolean;
  onArmPreview?: () => void;
  onPlaceOrder?: (draft: BacktestEntryOrderDraft) => void;
  onCancel?: () => void;
}

function formatPrice(value: number | null, precision: number): string {
  return value != null && Number.isFinite(value) ? value.toFixed(Math.max(0, Math.min(12, precision))) : '';
}

function formatUsd(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value);
}

function parsePriceInput(event: ChangeEvent<HTMLInputElement>, onDraft: (value: string) => void, onPrice: (price: number) => void) {
  const value = event.currentTarget.value;
  onDraft(value);
  if (value.trim() === '') return;
  const parsed = Number(value);
  if (Number.isFinite(parsed)) onPrice(parsed);
}

export function shouldClearPriceDraft(emittedValue: number | null, nextPrice: number | null): boolean {
  return !Object.is(emittedValue, nextPrice);
}

export function BacktestEntryPanel({
  instrument,
  account,
  costs,
  currentRevealedClose,
  entryType,
  onEntryTypeChange,
  direction,
  onDirectionChange,
  entryPrice,
  stopLossPrice,
  takeProfitPrice,
  onEntryPriceChange,
  onStopLossPriceChange,
  onTakeProfitPriceChange,
  autoSize,
  onAutoSizeChange,
  manualLots,
  onManualLotsChange,
  open,
  onOpenChange,
  showActions = false,
  previewActive = false,
  orderDisabled = false,
  orderPending = false,
  onArmPreview,
  onPlaceOrder,
  onCancel,
}: BacktestEntryPanelProps) {
  const generatedId = useId();
  const panelId = `backtest-entry-panel-${generatedId.replace(/:/g, '')}`;
  const [localOpen, setLocalOpen] = useState(true);
  const [localAutoSize, setLocalAutoSize] = useState(true);
  const [entryDraft, setEntryDraft] = useState<string | null>(null);
  const [stopDraft, setStopDraft] = useState<string | null>(null);
  const [targetDraft, setTargetDraft] = useState<string | null>(null);
  const emittedEntryPrice = useRef<number | null>(null);
  const emittedStopPrice = useRef<number | null>(null);
  const emittedTargetPrice = useRef<number | null>(null);
  const isOpen = open ?? localOpen;
  const useAutoSize = autoSize ?? localAutoSize;

  useEffect(() => {
    const shouldClear = shouldClearPriceDraft(emittedEntryPrice.current, entryPrice);
    emittedEntryPrice.current = null;
    if (shouldClear) setEntryDraft(null);
  }, [entryPrice]);
  useEffect(() => {
    const shouldClear = shouldClearPriceDraft(emittedStopPrice.current, stopLossPrice);
    emittedStopPrice.current = null;
    if (shouldClear) setStopDraft(null);
  }, [stopLossPrice]);
  useEffect(() => {
    const shouldClear = shouldClearPriceDraft(emittedTargetPrice.current, takeProfitPrice);
    emittedTargetPrice.current = null;
    if (shouldClear) setTargetDraft(null);
  }, [takeProfitPrice]);

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
  const drafts = [entryType === 'market' ? null : entryDraft, stopDraft, targetDraft];
  const allInputsComplete = drafts.every((draftValue) => draftValue == null
    || (draftValue.trim() !== '' && Number.isFinite(Number(draftValue))));
  const canPlaceOrder = sizing.canPlaceOrder && allInputsComplete && !orderDisabled && !orderPending;
  const draft = createBacktestEntryOrderDraft(sizingInput, sizing);
  const errorText = sizing.errors[0];
  const projectedOverBudget = sizing.projectedRiskPercent != null && sizing.projectedRiskPercent > 100;
  const initialBudget = Number.isFinite(account.currentBalanceUsd) && Number.isFinite(account.riskPercent)
    ? account.currentBalanceUsd * account.riskPercent / 100
    : null;

  function setExpanded(next: boolean) {
    if (open == null) setLocalOpen(next);
    onOpenChange?.(next);
  }

  function setAutoSize(next: boolean) {
    if (autoSize == null) setLocalAutoSize(next);
    onAutoSizeChange?.(next);
  }

  function handlePrimaryAction() {
    if (!canPlaceOrder || !draft) return;
    if (previewActive) onPlaceOrder?.(draft);
    else onArmPreview?.();
  }

  return (
    <aside
      className={`backtest-entry-panel${isOpen ? ' is-open' : ' is-collapsed'}`}
      aria-label="Simulated entry order"
      data-testid="backtest-entry-panel"
    >
      <header className="backtest-entry-panel-header">
        <div>
          <p className="backtest-entry-panel-eyebrow">Simulation</p>
          <h2 id={`${panelId}-heading`}>Entry order</h2>
        </div>
        <button
          type="button"
          className="backtest-entry-panel-collapse"
          aria-expanded={isOpen}
          aria-controls={`${panelId}-body`}
          aria-label={isOpen ? 'Collapse entry panel' : 'Expand entry panel'}
          title={isOpen ? 'Collapse entry panel' : 'Expand entry panel'}
          onClick={() => setExpanded(!isOpen)}
        >
          {isOpen ? <ChevronRight aria-hidden="true" size={18} /> : <ChevronLeft aria-hidden="true" size={18} />}
        </button>
      </header>

      <div id={`${panelId}-body`} className="backtest-entry-panel-body" hidden={!isOpen} aria-labelledby={`${panelId}-heading`}>
        <div className="backtest-entry-panel-type" role="group" aria-label="Entry type">
          <button type="button" aria-pressed={entryType === 'market'} onClick={() => onEntryTypeChange('market')}>Market</button>
          <button type="button" aria-pressed={entryType === 'limit'} onClick={() => onEntryTypeChange('limit')}>Limit</button>
        </div>

        <div className="backtest-entry-panel-direction" role="group" aria-label="Trade direction">
          <button type="button" aria-pressed={direction === 'long'} onClick={() => onDirectionChange('long')}>Long</button>
          <button type="button" aria-pressed={direction === 'short'} onClick={() => onDirectionChange('short')}>Short</button>
        </div>

        <div className="backtest-entry-panel-fields">
          <label htmlFor={`${panelId}-entry`}>Entry price</label>
          <input
            id={`${panelId}-entry`}
            aria-describedby={`${panelId}-entry-help`}
            type="text"
            inputMode="decimal"
            value={entryType === 'market' ? formatPrice(currentRevealedClose, instrument.pricePrecision) : entryDraft ?? formatPrice(entryPrice, instrument.pricePrecision)}
            readOnly={entryType === 'market'}
            onChange={(event) => parsePriceInput(event, setEntryDraft, (price) => {
              emittedEntryPrice.current = price;
              onEntryPriceChange(price);
            })}
          />
          <small id={`${panelId}-entry-help`}>{entryType === 'market' ? 'Fixed to the current revealed candle close.' : 'Moves with the whole bracket when dragged on the chart.'}</small>

          <label htmlFor={`${panelId}-stop`}>Stop-loss</label>
          <input
            id={`${panelId}-stop`}
            aria-describedby={`${panelId}-stop-help`}
            type="text"
            inputMode="decimal"
            value={stopDraft ?? formatPrice(stopLossPrice, instrument.pricePrecision)}
            onChange={(event) => parsePriceInput(event, setStopDraft, (price) => {
              emittedStopPrice.current = price;
              onStopLossPriceChange(price);
            })}
          />
          <small id={`${panelId}-stop-help`}>Editable here or by dragging its chart line.</small>

          <label htmlFor={`${panelId}-target`}>Take-profit</label>
          <input
            id={`${panelId}-target`}
            aria-describedby={`${panelId}-target-help`}
            type="text"
            inputMode="decimal"
            value={targetDraft ?? formatPrice(takeProfitPrice, instrument.pricePrecision)}
            onChange={(event) => parsePriceInput(event, setTargetDraft, (price) => {
              emittedTargetPrice.current = price;
              onTakeProfitPriceChange(price);
            })}
          />
          <small id={`${panelId}-target-help`}>Editable here or by dragging its chart line.</small>
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

        {showActions && (
          <div className="backtest-entry-panel-actions">
            <button
              type="button"
              className="backtest-entry-panel-place"
              disabled={!canPlaceOrder || !draft || (previewActive ? !onPlaceOrder : !onArmPreview)}
              onClick={handlePrimaryAction}
            >
              {orderPending ? 'Placing…' : previewActive ? 'Submit order' : 'Place order'}
            </button>
            {previewActive && onCancel && <button type="button" className="backtest-entry-panel-cancel" onClick={onCancel}>Cancel preview</button>}
          </div>
        )}
      </div>
      {!isOpen && (
        <button type="button" className="backtest-entry-panel-expand" aria-expanded={!isOpen} aria-controls={`${panelId}-body`} onClick={() => setExpanded(true)}>
          <ChevronLeft aria-hidden="true" size={16} />
          <span>Entry</span>
        </button>
      )}
    </aside>
  );
}

export default BacktestEntryPanel;
