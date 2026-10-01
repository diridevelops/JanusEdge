import { useEffect, useState } from 'react';
import type { BacktestOverlayPosition } from './BacktestPositionOverlay';

export interface BacktestWorkingOrder {
  id: string;
  side: 'buy' | 'sell';
  orderType: 'market' | 'limit';
  lots: number;
  entryPrice: number | null;
  stopLossPrice: number;
  takeProfitPrice: number;
  projectedRiskUsd: number;
}

interface BacktestOrdersAndPositionsProps {
  workingOrders: readonly BacktestWorkingOrder[];
  positions: readonly BacktestOverlayPosition[];
  pricePrecision: number;
  blindMode?: boolean;
  blindPricesAreNormalized?: boolean;
  currentClose?: number | null;
  toDisplayPrice?: (price: number) => number;
  toCanonicalPrice?: (price: number) => number;
  pending?: boolean;
  onCancelOrder: (orderId: string) => void;
  onMoveStop: (positionId: string, price: number) => void;
  onMoveTarget: (positionId: string, price: number) => void;
  onBreakEven: (positionId: string, price: number) => void;
  onClosePosition: (positionId: string) => void;
}

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 2,
});

/** Run-local pending orders and open exposure; neither is presented as a closed Journal trade. */
export function BacktestOrdersAndPositions({
  workingOrders,
  positions,
  pricePrecision,
  blindMode = false,
  blindPricesAreNormalized = false,
  currentClose = null,
  toDisplayPrice = (price) => price,
  toCanonicalPrice = (price) => price,
  pending = false,
  onCancelOrder,
  onMoveStop,
  onMoveTarget,
  onBreakEven,
  onClosePosition,
}: BacktestOrdersAndPositionsProps) {
  const [priceDrafts, setPriceDrafts] = useState<Record<string, { stop: string; target: string }>>({});

  useEffect(() => {
    setPriceDrafts(Object.fromEntries(positions.map((position) => [
      position.id,
      {
        stop: blindMode && !blindPricesAreNormalized ? '••••••' : String(toDisplayPrice(position.stopLossPrice)),
        target: blindMode && !blindPricesAreNormalized ? '••••••' : String(toDisplayPrice(position.takeProfitPrice)),
      },
    ])));
  }, [positions, toDisplayPrice]);

  function saveLevel(position: BacktestOverlayPosition, level: 'stop' | 'target') {
    const raw = priceDrafts[position.id]?.[level];
    if (blindMode && !blindPricesAreNormalized) return;
    const displayedValue = Number(raw);
    if (!raw?.trim() || !Number.isFinite(displayedValue)) return;
    const value = toCanonicalPrice(displayedValue);
    if (!Number.isFinite(value)) return;
    const stopReference = currentClose != null && Number.isFinite(currentClose)
      ? currentClose
      : position.weightedEntryPrice;
    const isValid = level === 'stop'
      ? (position.side === 'long' ? value < stopReference : value > stopReference)
      : (position.side === 'long' ? value > position.weightedEntryPrice : value < position.weightedEntryPrice);
    if (!isValid) return;
    if (level === 'stop') onMoveStop(position.id, value);
    else onMoveTarget(position.id, value);
  }

  return (
    <section className="grid gap-3 lg:grid-cols-2" aria-label="Backtest orders and positions">
      <div className="rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Working orders</h2>
        {workingOrders.length === 0 ? (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">No pending entry orders.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {workingOrders.map((order) => (
              <li key={order.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-gray-200 p-2 text-xs dark:border-gray-700">
                <span>{order.side.toUpperCase()} · {order.orderType} · {order.lots.toFixed(3)} lot{order.entryPrice == null ? '' : ` @ ${(blindMode ? '••••••' : toDisplayPrice(order.entryPrice).toFixed(pricePrecision))}`}</span>
                <span>Risk {usd.format(order.projectedRiskUsd)}</span>
                <button type="button" disabled={pending} onClick={() => onCancelOrder(order.id)} aria-label={`Cancel pending order ${order.id}`} className="rounded border border-gray-300 px-2 py-1 hover:bg-gray-100 disabled:opacity-40 dark:border-gray-600 dark:hover:bg-gray-800">Cancel</button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Open positions</h2>
        {positions.length === 0 ? (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">No open positions.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {positions.map((position) => (
              <li key={position.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded border border-gray-200 p-2 text-xs dark:border-gray-700">
                <span>{position.side.toUpperCase()} · {position.remainingLots.toFixed(3)} lot · Entry {blindMode ? 'masked' : position.weightedEntryPrice.toFixed(pricePrecision)}</span>
                <span>Unrealized {position.unrealizedPnlUsd == null ? '—' : usd.format(position.unrealizedPnlUsd)}</span>
                <span>Initial risk {usd.format(position.initialRiskUsd)}{position.stopMoved ? ' · stop-moved' : ''}</span>
                <div className="flex gap-1">
                  <button type="button" disabled={pending || currentClose == null || (position.side === 'long' ? currentClose <= position.weightedEntryPrice : currentClose >= position.weightedEntryPrice)} onClick={() => onBreakEven(position.id, position.weightedEntryPrice)} aria-label={`Move stop to break-even for position ${position.id}`} className="rounded border border-gray-300 px-2 py-1 disabled:opacity-40 dark:border-gray-600">BE</button>
                  <button type="button" disabled={pending} onClick={() => onClosePosition(position.id)} aria-label={`Close position ${position.id}`} className="rounded border border-rose-300 px-2 py-1 text-rose-700 hover:bg-rose-50 disabled:opacity-40 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950">Close</button>
                </div>
                <div className="flex w-full flex-wrap items-end gap-2">
                  <label className="text-gray-500 dark:text-gray-400">Stop
                    <input
                      className="ml-1 w-28 rounded border border-gray-300 bg-transparent px-1.5 py-1 text-gray-900 dark:border-gray-600 dark:text-gray-100"
                      type="number"
                      step={10 ** -pricePrecision}
                      value={priceDrafts[position.id]?.stop ?? (blindMode && !blindPricesAreNormalized ? '••••••' : toDisplayPrice(position.stopLossPrice))}
                      disabled={pending || (blindMode && !blindPricesAreNormalized)}
                      aria-label={`Stop price for position ${position.id}`}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setPriceDrafts((current) => ({
                          ...current,
                          [position.id]: {
                            stop: value,
                            target: current[position.id]?.target ?? String(toDisplayPrice(position.takeProfitPrice)),
                          },
                        }));
                      }}
                      onBlur={() => saveLevel(position, 'stop')}
                    />
                  </label>
                  <label className="text-gray-500 dark:text-gray-400">Target
                    <input
                      className="ml-1 w-28 rounded border border-gray-300 bg-transparent px-1.5 py-1 text-gray-900 dark:border-gray-600 dark:text-gray-100"
                      type="number"
                      step={10 ** -pricePrecision}
                      value={priceDrafts[position.id]?.target ?? (blindMode && !blindPricesAreNormalized ? '••••••' : toDisplayPrice(position.takeProfitPrice))}
                      disabled={pending || (blindMode && !blindPricesAreNormalized)}
                      aria-label={`Target price for position ${position.id}`}
                      onChange={(event) => {
                        const value = event.currentTarget.value;
                        setPriceDrafts((current) => ({
                          ...current,
                          [position.id]: {
                            stop: current[position.id]?.stop ?? String(toDisplayPrice(position.stopLossPrice)),
                            target: value,
                          },
                        }));
                      }}
                      onBlur={() => saveLevel(position, 'target')}
                    />
                  </label>
                </div>
                <div className="w-full text-gray-500 dark:text-gray-400">
                  Entry {blindMode ? '••••••' : toDisplayPrice(position.weightedEntryPrice).toFixed(pricePrecision)} · SL {blindMode ? '••••••' : toDisplayPrice(position.stopLossPrice).toFixed(pricePrecision)} · TP {blindMode ? '••••••' : toDisplayPrice(position.takeProfitPrice).toFixed(pricePrecision)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
