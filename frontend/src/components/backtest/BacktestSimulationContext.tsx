import { createContext, useContext } from 'react';
import type {
  BacktestEntryOrderDraft,
  BacktestEntryType,
  BacktestTradeDirection,
} from './backtestBracketMath';
import type { BacktestOverlayPosition } from './BacktestPositionOverlay';

export interface BacktestSimulationPreviewUi {
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
  currentBalanceUsd: number;
  canPlaceOrder: boolean;
  orderPending: boolean;
  invalidReason?: string;
  onEntryPriceChange: (price: number) => void;
  onStopLossPriceChange: (price: number) => void;
  onTakeProfitPriceChange: (price: number) => void;
  onPlaceOrder: (draft: BacktestEntryOrderDraft) => void;
  onCancel: () => void;
}

export interface BacktestSimulationChartUi {
  preview: BacktestSimulationPreviewUi;
  positions: BacktestOverlayPosition[];
  currentClose: number | null;
  pricePrecision: number;
  pipSize: number;
  disabled: boolean;
  onMoveStop: (positionId: string, displayedPrice: number) => void;
  onMoveTarget: (positionId: string, displayedPrice: number) => void;
  onBreakEven: (positionId: string, displayedPrice: number) => void;
  onClose: (positionId: string) => void;
}

const BacktestSimulationUiContext = createContext<BacktestSimulationChartUi | null>(null);

export const BacktestSimulationUiProvider = BacktestSimulationUiContext.Provider;

export function useBacktestSimulationChartUi() {
  return useContext(BacktestSimulationUiContext);
}
