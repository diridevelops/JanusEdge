import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';

export interface BacktestOverlayPosition {
  id: string;
  side: 'long' | 'short';
  remainingLots: number;
  weightedEntryPrice: number;
  stopLossPrice: number;
  takeProfitPrice: number;
  initialRiskUsd: number;
  unrealizedPnlUsd: number | null;
  stopMoved: boolean;
}

interface BacktestPositionOverlayProps {
  positions: readonly BacktestOverlayPosition[];
  pricePrecision: number;
  tickSize?: number;
  pipSize?: number;
  priceUnitLabel?: string;
  currentClose: number | null;
  priceToCoordinate: (price: number) => number | null;
  coordinateToPrice: (y: number) => number | null;
  onMoveStop: (positionId: string, price: number) => void;
  onMoveTarget: (positionId: string, price: number) => void;
  onBreakEven: (positionId: string, price: number) => void;
  onClose: (positionId: string) => void;
  disabled?: boolean;
}

interface ActiveDrag {
  pointerId: number;
  positionId: string;
  level: 'stop' | 'target';
  startPrice: number;
  startPointerPrice: number;
}

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 2,
});

function formatSignedAmount(value: number, precision: number): string {
  const rounded = Number(value.toFixed(precision));
  const sign = rounded > 0 ? '+' : rounded < 0 ? '-' : '';
  return `${sign}${Math.abs(rounded).toFixed(precision)}`;
}

function formatPositionPnlInInstrumentUnits(
  position: BacktestOverlayPosition,
  currentClose: number | null,
  pipSize: number,
  pricePrecision: number,
  priceUnitLabel: string
): string {
  if (currentClose == null || !Number.isFinite(currentClose)) return '—';
  const priceMove = position.side === 'long'
    ? currentClose - position.weightedEntryPrice
    : position.weightedEntryPrice - currentClose;
  if (!Number.isFinite(priceMove)) return '—';
  if (Number.isFinite(pipSize) && pipSize > 0) {
    return `${formatSignedAmount(priceMove / pipSize, 1)} ${priceUnitLabel}`;
  }
  return `${formatSignedAmount(priceMove, pricePrecision)} price`;
}

/** Keep a stop on the safe side of the latest close while allowing it past entry. */
export function clampPositionStopPrice(
  side: BacktestOverlayPosition['side'],
  candidate: number,
  entryPrice: number,
  currentClose: number | null,
  pricePrecision: number,
  configuredTickSize?: number
): number {
  const reference = currentClose != null && Number.isFinite(currentClose) ? currentClose : entryPrice;
  const tick = Number.isFinite(configuredTickSize) && (configuredTickSize ?? 0) > 0
    ? Number(configuredTickSize)
    : 10 ** -pricePrecision;
  const boundary = side === 'long' ? reference - tick : reference + tick;
  const bounded = side === 'long' ? Math.min(candidate, boundary) : Math.max(candidate, boundary);
  const steps = side === 'long'
    ? Math.floor(bounded / tick + 1e-10)
    : Math.ceil(bounded / tick - 1e-10);
  return Number((steps * tick).toPrecision(15));
}

/** Per-position chart levels. Entry stays fixed; stop and target edits are scoped by id. */
export function BacktestPositionOverlay({
  positions,
  pricePrecision,
  tickSize: configuredTickSize,
  pipSize = 0,
  priceUnitLabel = 'pips',
  currentClose,
  priceToCoordinate,
  coordinateToPrice,
  onMoveStop,
  onMoveTarget,
  onBreakEven,
  onClose,
  disabled = false,
}: BacktestPositionOverlayProps) {
  const tickSize = Number.isFinite(configuredTickSize) && (configuredTickSize ?? 0) > 0
    ? Number(configuredTickSize)
    : 10 ** -pricePrecision;
  const layerRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);
  const [drag, setDrag] = useState<ActiveDrag | null>(null);
  const [dragPrice, setDragPrice] = useState<number | null>(null);

  useEffect(() => {
    const element = layerRef.current;
    if (!element) return;
    const update = () => setHeight(element.getBoundingClientRect().height);
    update();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    observer?.observe(element);
    window.addEventListener('resize', update);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', update);
    };
  }, []);

  useEffect(() => {
    if (!drag) return;
    const move = (event: PointerEvent) => {
      if (event.pointerId !== drag.pointerId) return;
      const bounds = layerRef.current?.getBoundingClientRect();
      if (!bounds) return;
      const nextPointer = coordinateToPrice(event.clientY - bounds.top);
      if (nextPointer == null || !Number.isFinite(nextPointer)) return;
      const delta = nextPointer - drag.startPointerPrice;
      const position = positions.find((item) => item.id === drag.positionId);
      if (!position) return;
      if (drag.level === 'stop') {
        const candidate = drag.startPrice + delta;
        setDragPrice(clampPositionStopPrice(
          position.side,
          candidate,
          position.weightedEntryPrice,
          currentClose,
          pricePrecision,
          tickSize,
        ));
      } else {
        const candidate = drag.startPrice + delta;
        const bounded = position.side === 'long'
          ? Math.max(candidate, position.weightedEntryPrice + tickSize)
          : Math.min(candidate, position.weightedEntryPrice - tickSize);
        setDragPrice(Number((Math.round(bounded / tickSize) * tickSize).toPrecision(15)));
      }
    };
    const up = (event: PointerEvent) => {
      if (event.pointerId !== drag.pointerId) return;
      if (dragPrice != null) {
        if (drag.level === 'stop') onMoveStop(drag.positionId, dragPrice);
        else onMoveTarget(drag.positionId, dragPrice);
      }
      setDrag(null);
      setDragPrice(null);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
    };
  }, [coordinateToPrice, currentClose, drag, dragPrice, onMoveStop, onMoveTarget, positions, pricePrecision, tickSize]);

  return (
    <div ref={layerRef} className="pointer-events-none absolute inset-0 z-20 overflow-hidden" data-testid="backtest-position-overlay">
      {positions.map((position, index) => {
        const levels = [
          { name: 'entry' as const, price: position.weightedEntryPrice, color: '#0ea5a5', style: 'solid' },
          { name: 'stop' as const, price: position.stopLossPrice, color: '#f43f5e', style: 'dashed' },
          { name: 'target' as const, price: position.takeProfitPrice, color: '#10b981', style: 'solid' },
        ];
        const beAllowed = currentClose != null && Number.isFinite(currentClose)
          && (position.side === 'long'
            ? currentClose > position.weightedEntryPrice
            : currentClose < position.weightedEntryPrice);
        const entryY = priceToCoordinate(position.weightedEntryPrice) ?? 10;
        const shortMarkerY = entryY - index * 16;
        const markerAboveEntry = position.side === 'short' && shortMarkerY >= 28;
        const riskMarkerY = markerAboveEntry ? shortMarkerY : entryY + index * 16;

        return (
          <div key={position.id} data-position-id={position.id} aria-label={`${position.side} position ${position.id}`}>
            {levels.map((level) => {
              const displayedPrice = drag?.positionId === position.id
                && drag.level === level.name && dragPrice != null
                ? dragPrice
                : level.price;
              const y = priceToCoordinate(displayedPrice);
              if (y == null || !Number.isFinite(y) || y < 0 || y > height) return null;
              const draggable = level.name !== 'entry';
              return (
                <div key={level.name} className="absolute left-[38px] right-[54px] pointer-events-none" style={{ top: y }}>
                  <div style={{ borderTop: `1px ${level.style} ${level.color}`, opacity: 0.9 }} />
                  {draggable ? (
                    <button
                      type="button"
                      disabled={disabled}
                      className="pointer-events-auto absolute -top-3 right-0 max-w-[42%] truncate rounded px-1.5 py-0.5 text-[10px] font-semibold text-white shadow"
                      style={{ backgroundColor: level.color, marginTop: index * 15 }}
                      aria-label={`Move ${level.name === 'stop' ? 'stop-loss' : 'take-profit'} for position ${position.id}, ${level.price.toFixed(pricePrecision)}`}
                      onPointerDown={(event: ReactPointerEvent<HTMLButtonElement>) => {
                        const bounds = layerRef.current?.getBoundingClientRect();
                        if (!bounds) return;
                        const pointerPrice = coordinateToPrice(event.clientY - bounds.top);
                        if (pointerPrice == null || !Number.isFinite(pointerPrice)) return;
                        event.preventDefault();
                        event.stopPropagation();
                        setDrag({
                          pointerId: event.pointerId,
                          positionId: position.id,
                          level: level.name,
                          startPrice: level.price,
                          startPointerPrice: pointerPrice,
                        });
                        setDragPrice(level.price);
                      }}
                      onKeyDown={(event) => {
                        if (disabled || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) return;
                        event.preventDefault();
                        const delta = event.key === 'ArrowUp' ? 1 : -1;
                        const next = level.price + delta * tickSize;
                        if (level.name === 'stop') {
                          onMoveStop(position.id, clampPositionStopPrice(
                            position.side,
                            next,
                            position.weightedEntryPrice,
                            currentClose,
                            pricePrecision,
                            tickSize,
                          ));
                        }
                        else onMoveTarget(position.id, Number((Math.round(next / tickSize) * tickSize).toPrecision(15)));
                      }}
                    >
                      {level.name === 'stop' ? 'SL' : 'TP'} {displayedPrice.toFixed(pricePrecision)}
                    </button>
                  ) : (
                    <span className="absolute -top-3 left-0 rounded px-1.5 py-0.5 text-[10px] font-semibold text-white shadow" style={{ backgroundColor: level.color }}>
                      {position.side.toUpperCase()} · {position.remainingLots.toFixed(3)} lot · {position.unrealizedPnlUsd == null ? '—' : usd.format(position.unrealizedPnlUsd)}
                    </span>
                  )}
                </div>
              );
            })}
            <div className="pointer-events-auto absolute right-14 flex items-center gap-0.5 whitespace-nowrap rounded-md border border-slate-500/40 bg-slate-950/90 px-1 py-0.5 text-[10px] leading-none text-white shadow" style={{
              top: Math.min(height - 28, Math.max(2, riskMarkerY)),
              transform: markerAboveEntry ? 'translateY(calc(-100% - 2px))' : 'translateY(2px)',
            }}>
              <span className="sr-only" title={`Initial risk ${usd.format(position.initialRiskUsd)}${position.stopMoved ? ' · stop-moved' : ''}`}>
                Risk {usd.format(position.initialRiskUsd)}{position.stopMoved ? ' · moved' : ''}
              </span>
              <span
                className="px-1"
                title={`USD unrealized P&L ${position.unrealizedPnlUsd == null ? 'unavailable' : usd.format(position.unrealizedPnlUsd)}`}
              >
                P&amp;L {formatPositionPnlInInstrumentUnits(position, currentClose, pipSize, pricePrecision, priceUnitLabel)}
              </span>
              <button type="button" className="rounded px-1.5 py-0.5 leading-none hover:bg-white/15 disabled:opacity-40" aria-label={`Move stop to break-even for position ${position.id}`} title="Move stop to entry" disabled={!beAllowed || disabled} onClick={() => onBreakEven(position.id, position.weightedEntryPrice)}>BE</button>
              <button type="button" className="rounded px-1.5 py-0.5 leading-none hover:bg-rose-500/30 disabled:opacity-40" aria-label={`Close position ${position.id}`} title="Close this position" disabled={disabled} onClick={() => onClose(position.id)}>×</button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
