import type { Execution } from '../types/execution.types';

export function getExecutionMarkerStyle(side: Execution['side']) {
  const isBuy = side.toLowerCase() === 'buy';
  return {
    position: isBuy ? 'belowBar' as const : 'aboveBar' as const,
    color: isBuy ? '#22c55e' : '#ef4444',
    shape: isBuy ? 'arrowUp' as const : 'arrowDown' as const,
    label: isBuy ? 'Buy' : 'Sell',
  };
}
