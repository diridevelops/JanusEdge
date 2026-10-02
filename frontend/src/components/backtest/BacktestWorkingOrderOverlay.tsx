import { useEffect, useRef, useState } from 'react';

export interface BacktestWorkingOrderOverlayItem {
  id: string;
  side: 'buy' | 'sell';
  orderType: 'market' | 'limit';
  lots: number;
  entryPrice: number;
}

interface BacktestWorkingOrderOverlayProps {
  orders: readonly BacktestWorkingOrderOverlayItem[];
  pricePrecision: number;
  priceToCoordinate: (price: number) => number | null;
  onCancel: (orderId: string) => void;
  disabled?: boolean;
}

/** Dashed, cancelable entry levels for pending orders; filled positions use their own overlay. */
export function BacktestWorkingOrderOverlay({
  orders,
  pricePrecision,
  priceToCoordinate,
  onCancel,
  disabled = false,
}: BacktestWorkingOrderOverlayProps) {
  const layerRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    const element = layerRef.current;
    if (!element) return;
    const updateHeight = () => setHeight(element.getBoundingClientRect().height);
    updateHeight();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(updateHeight);
    observer?.observe(element);
    window.addEventListener('resize', updateHeight);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', updateHeight);
    };
  }, []);

  return (
    <div ref={layerRef} className="backtest-working-order-overlay" data-testid="backtest-working-order-overlay">
      {orders.map((order, index) => {
        const y = priceToCoordinate(order.entryPrice);
        if (y == null || !Number.isFinite(y) || y < 0 || y > height) return null;
        const labelTop = Math.min(Math.max(1, y - 10 + (index % 3) * 14), Math.max(1, height - 23));
        const orderDescription = `Pending ${order.side.toUpperCase()} ${order.orderType.toUpperCase()} order, ${order.lots.toFixed(3)} lots at ${order.entryPrice.toFixed(pricePrecision)}`;

        return (
          <div key={order.id} className="backtest-working-order-marker" role="group" aria-label={orderDescription}>
            <div className="backtest-working-order-line" style={{ top: y }} aria-hidden="true" />
            <span className="backtest-working-order-label" style={{ top: labelTop }}>
              PENDING {order.side.toUpperCase()} {order.orderType.toUpperCase()} · {order.lots.toFixed(3)} @ {order.entryPrice.toFixed(pricePrecision)}
            </span>
            <button
              type="button"
              className="backtest-working-order-cancel"
              style={{ top: labelTop }}
              aria-label={`Cancel pending order ${order.id} from chart`}
              title={`${orderDescription}. Cancel order`}
              disabled={disabled}
              onClick={() => onCancel(order.id)}
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default BacktestWorkingOrderOverlay;
