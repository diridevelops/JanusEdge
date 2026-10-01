import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import {
  roundPriceToPrecision,
  type BacktestEntryOrderDraft,
  type BacktestEntryType,
  type BacktestTradeDirection,
} from './backtestBracketMath';

type DragTarget = 'bracket' | 'stop' | 'target';

interface ActiveDrag {
  pointerId: number;
  target: DragTarget;
  startPointerPrice: number;
  startPrices: { entryPrice: number; stopLossPrice: number; takeProfitPrice: number };
}

export interface BacktestBracketPreviewProps {
  visible: boolean;
  entryType: BacktestEntryType;
  direction: BacktestTradeDirection;
  entryPrice: number;
  stopLossPrice: number;
  takeProfitPrice: number;
  pricePrecision: number;
  pipSize: number;
  quantityLots: number | null;
  autoSize: boolean;
  riskBudgetUsd: number | null;
  projectedRiskUsd: number | null;
  projectedRewardUsd: number | null;
  riskRewardRatio: number | null;
  currentBalanceUsd?: number;
  canPlaceOrder: boolean;
  invalidReason?: string;
  /** Maps a price to a y-coordinate relative to this overlay's top edge. */
  priceToCoordinate: (price: number) => number | null;
  /** Maps a y-coordinate relative to this overlay's top edge to a price. */
  coordinateToPrice: (y: number) => number | null;
  /** Horizontal plot bounds in overlay-local pixels. Defaults leave room for chart axes. */
  plotLeftPx?: number;
  plotRightPx?: number;
  showActionBar?: boolean;
  onEntryPriceChange: (price: number) => void;
  onStopLossPriceChange: (price: number) => void;
  onTakeProfitPriceChange: (price: number) => void;
  onPlaceOrder?: (draft: BacktestEntryOrderDraft) => void;
  onCancel?: () => void;
}

function formatPrice(value: number, precision: number): string {
  return Number.isFinite(value) ? value.toFixed(Math.max(0, Math.min(12, precision))) : '—';
}

function formatUsd(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function BacktestBracketPreview({
  visible,
  entryType,
  direction,
  entryPrice,
  stopLossPrice,
  takeProfitPrice,
  pricePrecision,
  pipSize,
  quantityLots,
  autoSize,
  riskBudgetUsd,
  projectedRiskUsd,
  projectedRewardUsd,
  riskRewardRatio,
  currentBalanceUsd,
  canPlaceOrder,
  invalidReason,
  priceToCoordinate,
  coordinateToPrice,
  plotLeftPx,
  plotRightPx,
  showActionBar = true,
  onEntryPriceChange,
  onStopLossPriceChange,
  onTakeProfitPriceChange,
  onPlaceOrder,
  onCancel,
}: BacktestBracketPreviewProps) {
  const layerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [activeDrag, setActiveDrag] = useState<ActiveDrag | null>(null);

  useEffect(() => {
    const element = layerRef.current;
    if (!element) return;
    const updateSize = () => {
      const bounds = element.getBoundingClientRect();
      setSize({ width: bounds.width, height: bounds.height });
    };
    updateSize();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateSize);
      return () => window.removeEventListener('resize', updateSize);
    }
    const observer = new ResizeObserver(updateSize);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!activeDrag) return;
    const onMove = (event: PointerEvent) => {
      if (event.pointerId !== activeDrag.pointerId) return;
      const element = layerRef.current;
      if (!element) return;
      const bounds = element.getBoundingClientRect();
      const currentPointerPrice = coordinateToPrice(event.clientY - bounds.top);
      if (currentPointerPrice == null || !Number.isFinite(currentPointerPrice)) return;
      const tick = 10 ** -pricePrecision;
      const rawDelta = currentPointerPrice - activeDrag.startPointerPrice;
      const { entryPrice: startEntry, stopLossPrice: startStop, takeProfitPrice: startTarget } = activeDrag.startPrices;

      if (activeDrag.target === 'bracket' && entryType === 'limit') {
        const movedEntry = roundPriceToPrecision(startEntry + rawDelta, pricePrecision);
        const delta = movedEntry - startEntry;
        onEntryPriceChange(movedEntry);
        onStopLossPriceChange(roundPriceToPrecision(startStop + delta, pricePrecision));
        onTakeProfitPriceChange(roundPriceToPrecision(startTarget + delta, pricePrecision));
        return;
      }

      if (activeDrag.target === 'stop') {
        const candidate = roundPriceToPrecision(startStop + rawDelta, pricePrecision);
        const validStop = direction === 'long'
          ? Math.min(candidate, entryPrice - tick)
          : Math.max(candidate, entryPrice + tick);
        onStopLossPriceChange(roundPriceToPrecision(validStop, pricePrecision));
      } else if (activeDrag.target === 'target') {
        const candidate = roundPriceToPrecision(startTarget + rawDelta, pricePrecision);
        const validTarget = direction === 'long'
          ? Math.max(candidate, entryPrice + tick)
          : Math.min(candidate, entryPrice - tick);
        onTakeProfitPriceChange(roundPriceToPrecision(validTarget, pricePrecision));
      }
    };
    const onUp = (event: PointerEvent) => {
      if (event.pointerId === activeDrag.pointerId) setActiveDrag(null);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
    };
  }, [
    activeDrag,
    coordinateToPrice,
    direction,
    entryPrice,
    entryType,
    onEntryPriceChange,
    onStopLossPriceChange,
    onTakeProfitPriceChange,
    pricePrecision,
  ]);

  if (!visible) return null;

  const plotLeft = clamp(plotLeftPx ?? 38, 0, Math.max(0, size.width));
  const plotRight = clamp(plotRightPx ?? size.width - 54, plotLeft, Math.max(plotLeft, size.width));
  const plotWidth = plotRight - plotLeft;
  const entryY = priceToCoordinate(entryPrice);
  const stopY = priceToCoordinate(stopLossPrice);
  const targetY = priceToCoordinate(takeProfitPrice);
  if (size.width <= 0 || size.height <= 0 || plotWidth <= 0
    || entryY == null || stopY == null || targetY == null
    || ![entryY, stopY, targetY].every(Number.isFinite)) {
    return <div ref={layerRef} className="backtest-bracket-preview-layer" aria-hidden="true" />;
  }

  const rewardTop = Math.min(entryY, targetY);
  const rewardHeight = Math.max(1, Math.abs(entryY - targetY));
  const riskTop = Math.min(entryY, stopY);
  const riskHeight = Math.max(1, Math.abs(entryY - stopY));
  const fullTop = Math.min(entryY, stopY, targetY);
  const fullBottom = Math.max(entryY, stopY, targetY);
  const entryLabelTop = clamp(entryY - 27, 2, Math.max(2, size.height - 25));
  const targetLabelTop = clamp(targetY - 22, 2, Math.max(2, size.height - 22));
  const stopLabelTop = clamp(stopY + 7, 2, Math.max(2, size.height - 22));
  const toolbarTop = clamp(entryY + 12, 2, Math.max(2, size.height - 34));
  const toolbarLeft = plotLeft + Math.min(plotWidth * 0.3, 110);
  const targetDistancePips = pipSize > 0 ? Math.abs(takeProfitPrice - entryPrice) / pipSize : null;
  const stopDistancePips = pipSize > 0 ? Math.abs(entryPrice - stopLossPrice) / pipSize : null;
  const rewardPct = projectedRewardUsd != null && currentBalanceUsd != null && currentBalanceUsd > 0
    ? projectedRewardUsd / currentBalanceUsd * 100
    : null;
  const quantityText = quantityLots != null && Number.isFinite(quantityLots) ? `${quantityLots.toFixed(3)} lot` : '— lot';
  const draft: BacktestEntryOrderDraft | null = canPlaceOrder && quantityLots != null
    && riskBudgetUsd != null && projectedRiskUsd != null
    ? { entryType, direction, entryPrice, stopLossPrice, takeProfitPrice, quantityLots, autoSize, riskBudgetUsd, projectedRiskUsd }
    : null;
  const groupStartY = fullTop;
  const groupHeight = Math.max(1, fullBottom - fullTop);

  function beginDrag(event: ReactPointerEvent<HTMLElement>, target: DragTarget) {
    if (target === 'bracket' && entryType !== 'limit') return;
    const bounds = layerRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const pointerPrice = coordinateToPrice(event.clientY - bounds.top);
    if (pointerPrice == null || !Number.isFinite(pointerPrice)) return;
    event.preventDefault();
    event.stopPropagation();
    setActiveDrag({
      pointerId: event.pointerId,
      target,
      startPointerPrice: pointerPrice,
      startPrices: { entryPrice, stopLossPrice, takeProfitPrice },
    });
  }

  function nudge(target: DragTarget, delta: number) {
    const tick = 10 ** -pricePrecision;
    if (target === 'bracket' && entryType === 'limit') {
      onEntryPriceChange(roundPriceToPrecision(entryPrice + delta, pricePrecision));
      onStopLossPriceChange(roundPriceToPrecision(stopLossPrice + delta, pricePrecision));
      onTakeProfitPriceChange(roundPriceToPrecision(takeProfitPrice + delta, pricePrecision));
    } else if (target === 'stop') {
      const next = direction === 'long'
        ? Math.min(stopLossPrice + delta, entryPrice - tick)
        : Math.max(stopLossPrice + delta, entryPrice + tick);
      onStopLossPriceChange(roundPriceToPrecision(next, pricePrecision));
    } else if (target === 'target') {
      const next = direction === 'long'
        ? Math.max(takeProfitPrice + delta, entryPrice + tick)
        : Math.min(takeProfitPrice + delta, entryPrice - tick);
      onTakeProfitPriceChange(roundPriceToPrecision(next, pricePrecision));
    }
  }

  function onLineKeyDown(event: ReactKeyboardEvent<HTMLElement>, target: DragTarget) {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    nudge(target, event.key === 'ArrowUp' ? 10 ** -pricePrecision : -(10 ** -pricePrecision));
  }

  const bracketStyle: CSSProperties = { left: plotLeft, width: plotWidth };
  const groupStyle: CSSProperties = { ...bracketStyle, top: groupStartY, height: groupHeight };
  const entryLineStyle: CSSProperties = { ...bracketStyle, top: entryY - 10 };
  const stopLineStyle: CSSProperties = { ...bracketStyle, top: stopY - 10 };
  const targetLineStyle: CSSProperties = { ...bracketStyle, top: targetY - 10 };

  return (
    <div
      ref={layerRef}
      className={`backtest-bracket-preview-layer${activeDrag ? ' is-dragging' : ''}`}
      role="group"
      aria-label={`Temporary ${entryType} ${direction} entry bracket. Entry ${formatPrice(entryPrice, pricePrecision)}, stop ${formatPrice(stopLossPrice, pricePrecision)}, target ${formatPrice(takeProfitPrice, pricePrecision)}.`}
      data-testid="backtest-bracket-preview"
    >
      <div
        className="backtest-bracket-preview-zone backtest-bracket-preview-zone--reward"
        style={{ ...bracketStyle, top: rewardTop, height: rewardHeight }}
        aria-hidden="true"
      />
      <div
        className="backtest-bracket-preview-zone backtest-bracket-preview-zone--risk"
        style={{ ...bracketStyle, top: riskTop, height: riskHeight }}
        aria-hidden="true"
      />
      <div
        className="backtest-bracket-preview-selection-frame"
        style={{ ...bracketStyle, top: fullTop, height: groupHeight }}
        aria-hidden="true"
      />

      {entryType === 'limit' && (
        <button
          type="button"
          className="backtest-bracket-preview-group-drag"
          style={groupStyle}
          aria-label={`Move complete limit bracket for ${direction} entry`}
          title="Drag to move entry, stop, and target together"
          onPointerDown={(event) => beginDrag(event, 'bracket')}
          onKeyDown={(event) => onLineKeyDown(event, 'bracket')}
        />
      )}

      <div className="backtest-bracket-preview-level backtest-bracket-preview-level--target" style={{ ...bracketStyle, top: targetY }} aria-hidden="true" />
      <button
        type="button"
        className="backtest-bracket-preview-dragline backtest-bracket-preview-dragline--target"
        style={targetLineStyle}
        aria-label={`Move take-profit. Current target ${formatPrice(takeProfitPrice, pricePrecision)}.`}
        title="Drag to move take-profit; use arrow keys to adjust by one tick"
        onPointerDown={(event) => beginDrag(event, 'target')}
        onKeyDown={(event) => onLineKeyDown(event, 'target')}
      >
        <span className="backtest-bracket-preview-handle backtest-bracket-preview-handle--left" aria-hidden="true" />
        <span className="backtest-bracket-preview-handle backtest-bracket-preview-handle--center" aria-hidden="true" />
        <span className="backtest-bracket-preview-handle backtest-bracket-preview-handle--right" aria-hidden="true" />
      </button>

      <div className="backtest-bracket-preview-level backtest-bracket-preview-level--stop" style={{ ...bracketStyle, top: stopY }} aria-hidden="true" />
      <button
        type="button"
        className="backtest-bracket-preview-dragline backtest-bracket-preview-dragline--stop"
        style={stopLineStyle}
        aria-label={`Move stop-loss. Current stop ${formatPrice(stopLossPrice, pricePrecision)}.`}
        title="Drag to move stop-loss; use arrow keys to adjust by one tick"
        onPointerDown={(event) => beginDrag(event, 'stop')}
        onKeyDown={(event) => onLineKeyDown(event, 'stop')}
      >
        <span className="backtest-bracket-preview-handle backtest-bracket-preview-handle--left" aria-hidden="true" />
        <span className="backtest-bracket-preview-handle backtest-bracket-preview-handle--center" aria-hidden="true" />
        <span className="backtest-bracket-preview-handle backtest-bracket-preview-handle--right" aria-hidden="true" />
      </button>

      <div className="backtest-bracket-preview-level backtest-bracket-preview-level--entry" style={{ ...bracketStyle, top: entryY }} aria-hidden="true" />
      {entryType === 'limit' ? (
        <button
          type="button"
          className="backtest-bracket-preview-dragline backtest-bracket-preview-dragline--entry"
          style={entryLineStyle}
          aria-label={`Move limit entry and complete bracket. Current entry ${formatPrice(entryPrice, pricePrecision)}.`}
          title="Drag to move entry, stop, and target together; use arrow keys to move one tick"
          onPointerDown={(event) => beginDrag(event, 'bracket')}
          onKeyDown={(event) => onLineKeyDown(event, 'bracket')}
        >
          <span className="backtest-bracket-preview-handle backtest-bracket-preview-handle--left" aria-hidden="true" />
          <span className="backtest-bracket-preview-handle backtest-bracket-preview-handle--center" aria-hidden="true" />
          <span className="backtest-bracket-preview-handle backtest-bracket-preview-handle--right" aria-hidden="true" />
        </button>
      ) : (
        <div
          className="backtest-bracket-preview-market-entry"
          style={{ ...bracketStyle, top: entryY }}
          aria-label={`Market entry fixed at the current revealed close ${formatPrice(entryPrice, pricePrecision)}.`}
        />
      )}

      <div className="backtest-bracket-preview-summary" style={{ left: plotLeft + Math.min(plotWidth * 0.12, 42), top: entryLabelTop }}>
        <span>{direction.toUpperCase()}</span>
        <span>RR {riskRewardRatio == null || !Number.isFinite(riskRewardRatio) ? '—' : riskRewardRatio.toFixed(2)}</span>
        <span>Qty: {quantityText}</span>
        <span>Risk: {formatUsd(projectedRiskUsd)}</span>
      </div>
      <div className="backtest-bracket-preview-label backtest-bracket-preview-label--target" style={{ left: plotLeft + Math.min(plotWidth * 0.14, 44), top: targetLabelTop }}>
        <span>TP {formatPrice(takeProfitPrice, pricePrecision)}</span>
        {targetDistancePips != null && <span>{targetDistancePips.toFixed(1)} pips</span>}
        {projectedRewardUsd != null && <span>{formatUsd(projectedRewardUsd)}{rewardPct != null ? ` · ${rewardPct.toFixed(2)}%` : ''}</span>}
      </div>
      <div className="backtest-bracket-preview-label backtest-bracket-preview-label--stop" style={{ left: plotLeft + Math.min(plotWidth * 0.14, 44), top: stopLabelTop }}>
        <span>SL {formatPrice(stopLossPrice, pricePrecision)}</span>
        {stopDistancePips != null && <span>{stopDistancePips.toFixed(1)} pips</span>}
      </div>

      {showActionBar && (
        <div className="backtest-bracket-preview-actions" style={{ left: toolbarLeft, top: toolbarTop }}>
          <button
            type="button"
            className="backtest-bracket-preview-place"
            disabled={!canPlaceOrder || !draft || !onPlaceOrder}
            title={invalidReason || (autoSize ? `Auto-sized to ${quantityText}` : `Manual size ${quantityText}`)}
            onClick={() => draft && onPlaceOrder?.(draft)}
          >
            <span aria-hidden="true">↗</span> Place order
          </button>
          {onCancel && (
            <button type="button" className="backtest-bracket-preview-cancel" aria-label="Cancel entry preview" title="Cancel entry preview" onClick={onCancel}>
              Cancel
            </button>
          )}
        </div>
      )}
      {invalidReason && !canPlaceOrder && <span className="backtest-bracket-preview-validation" role="status">{invalidReason}</span>}
    </div>
  );
}

export default BacktestBracketPreview;
