import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Maximize2 } from 'lucide-react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { getBacktestChartWorkspace, getBacktestRun, saveBacktestChartWorkspace } from '../api/backtests.api';
import {
  calculateBacktestBracketSizing,
  createBacktestEntryOrderDraft,
  createDefaultBacktestBracket,
  roundPriceToPrecision,
} from '../components/backtest/backtestBracketMath';
import { BacktestEntryPanel } from '../components/backtest/BacktestEntryPanel';
import { BacktestOrdersAndPositions, type BacktestWorkingOrder } from '../components/backtest/BacktestOrdersAndPositions';
import { BacktestSimulationUiProvider, type BacktestSimulationChartUi } from '../components/backtest/BacktestSimulationContext';
import { BacktestChartWorkspace } from '../components/backtest/BacktestChartWorkspace';
import { BacktestReplayControls } from '../components/backtest/BacktestReplayControls';
import { Spinner } from '../components/ui/Spinner';
import { useBacktestChartSync } from '../hooks/useBacktestChartSync';
import { useBacktestReplay } from '../hooks/useBacktestReplay';
import { createBacktestSimulationOperationRequest, useBacktestSimulation } from '../hooks/useBacktestSimulation';
import { useAuth } from '../hooks/useAuth';
import { useChartColors } from '../hooks/useChartColors';
import type { BacktestChartTab, BacktestRunDetail } from '../types/backtest.types';
import {
  extractBacktestWorkspaceTabs,
  initializeBacktestWorkspace,
  type BacktestWorkspaceApi,
} from '../utils/backtestWorkspace';
import type { WorkspaceLayout } from '@getcandlekit/charts/react/workspace';
import '../styles/backtest-candlekit.css';
import type { AppLayoutOutletContext } from '../components/layout/AppLayout';
import { createCandleKitControlsAdapter } from '../utils/backtestReplay';
import { getBacktestDisplayPricePrecision, normalizeBacktestPrice } from '../utils/backtestPriceFormat';
import type {
  BacktestEntryInstrument,
  BacktestEntryOrderDraft,
  BacktestEntryType,
  BacktestTradeDirection,
} from '../components/backtest/backtestBracketMath';

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return 'Could not load this Backtest run.';
}

function ignoreRejectedMutation(promise: Promise<unknown>): void {
  void promise.catch(() => undefined);
}

/** Fetch the selected ready run; preparing runs remain on the run-list route. */
export function BacktestReplayPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<BacktestRunDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!runId) {
      setIsLoading(false);
      setLoadError('The Backtest run id is missing.');
      return () => { cancelled = true; };
    }

    setIsLoading(true);
    setLoadError(null);
    void getBacktestRun(runId)
      .then((detail) => {
        if (!cancelled) setRun(detail);
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(getErrorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => { cancelled = true; };
  }, [attempt, runId]);

  if (isLoading) {
    return (
      <div className="flex min-h-64 items-center justify-center" aria-label="Loading Backtest run">
        <Spinner />
      </div>
    );
  }

  if (loadError || !run) {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-red-200 bg-white p-6 dark:border-red-900 dark:bg-gray-900">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Replay unavailable</h1>
        <p className="mt-2 text-sm text-red-700 dark:text-red-300" role="alert">
          {loadError ?? 'Could not find this Backtest run.'}
        </p>
        <div className="mt-4 flex gap-3">
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
            className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Retry
          </button>
          <Link to="/backtest/runs" className="rounded-md px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800">
            Back to runs
          </Link>
        </div>
      </section>
    );
  }

  if (run.status !== 'ready' && run.status !== 'complete') {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Run is still preparing</h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
          Replay charts are available after preparation completes.
        </p>
        <Link to="/backtest/runs" className="mt-4 inline-flex rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700">
          View run progress
        </Link>
      </section>
    );
  }

  if (run.blind_mode && (
    run.normalized_reference_price == null
    || !Number.isFinite(run.normalized_reference_price)
    || run.normalized_reference_price === 0
  )) {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-red-200 bg-white p-6 dark:border-red-900 dark:bg-gray-900">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Replay unavailable</h1>
        <p className="mt-2 text-sm text-red-700 dark:text-red-300" role="alert">
          This Blind run is missing a valid normalized-price reference.
        </p>
        <Link to="/backtest/runs" className="mt-4 inline-flex rounded-md px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800">
          Back to runs
        </Link>
      </section>
    );
  }

  return <BacktestReplayRunView key={run.id} run={run} />;
}

function BacktestReplayRunView({ run }: { run: BacktestRunDetail }) {
  const api = useMemo<BacktestWorkspaceApi>(() => ({
    get: getBacktestChartWorkspace,
    save: saveBacktestChartWorkspace,
  }), []);
  const [workspace, setWorkspace] = useState<{
    layout: WorkspaceLayout;
    revision: number;
  } | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setWorkspace(null);
    setWorkspaceError(null);
    void initializeBacktestWorkspace(run.id, api)
      .then((initialized) => {
        if (!cancelled) setWorkspace(initialized);
      })
      .catch((error: unknown) => {
        if (!cancelled) setWorkspaceError(getErrorMessage(error));
      });
    return () => { cancelled = true; };
  }, [api, loadAttempt, run.id]);

  if (workspaceError) {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-red-200 bg-white p-6 dark:border-red-900 dark:bg-gray-900">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Chart workspace unavailable</h1>
        <p className="mt-2 text-sm text-red-700 dark:text-red-300" role="alert">{workspaceError}</p>
        <button
          type="button"
          onClick={() => setLoadAttempt((value) => value + 1)}
          className="mt-4 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Retry workspace load
        </button>
      </section>
    );
  }

  if (!workspace) {
    return (
      <div className="flex min-h-64 items-center justify-center gap-3 text-sm text-gray-600 dark:text-gray-300" aria-label="Loading chart workspace">
        <Spinner />
        Loading the saved chart workspace…
      </div>
    );
  }

  return (
    <BacktestReplayWorkspaceRun
      run={run}
      initialLayout={workspace.layout}
      revision={workspace.revision}
    />
  );
}

function BacktestReplayWorkspaceRun({
  run,
  initialLayout,
  revision,
}: {
  run: BacktestRunDetail;
  initialLayout: WorkspaceLayout;
  revision: number;
}) {
  const { isReplayMaximized, setReplayMaximized } = useOutletContext<AppLayoutOutletContext>();
  const colors = useChartColors();
  const { user } = useAuth();
  const [simulationSidebarCollapsed, setSimulationSidebarCollapsed] = useState(false);
  const [tabs, setTabs] = useState<BacktestChartTab[]>(() => (
    extractBacktestWorkspaceTabs(initialLayout)
  ));
  const replay = useBacktestReplay(run, tabs, { simulationDriven: true });
  const simulation = useBacktestSimulation(run.id, replay.status === 'ready');
  const chartSync = useBacktestChartSync(tabs, run.instrument, replay.controller);
  const simulationNavigationRef = useRef({ simulation, replayStartIndex: run.snapshot?.replay_start_source_index ?? 0 });
  simulationNavigationRef.current = { simulation, replayStartIndex: run.snapshot?.replay_start_source_index ?? 0 };
  const selectedReplayTimes = useMemo(
    () => replay.allCandleTimes.slice(run.snapshot?.replay_start_source_index ?? 0),
    [replay.allCandleTimes, run.snapshot?.replay_start_source_index]
  );
  const simulationControls = useMemo(() => createCandleKitControlsAdapter(
    replay.controller,
    selectedReplayTimes,
    {
      canRewind: () => {
        const state = simulationNavigationRef.current.simulation.state;
        return Boolean(state && !state.backward_navigation_locked && state.status === 'ready');
      },
      onAdvance: async (selectedIndex, timeMs) => {
        const current = simulationNavigationRef.current.simulation.state;
        if (!current) throw new Error('Simulation state is loading.');
        await simulationNavigationRef.current.simulation.advance({
          ...createBacktestSimulationOperationRequest(current.control_revision),
          target_source_index: simulationNavigationRef.current.replayStartIndex + selectedIndex,
        });
        void timeMs;
      },
      onRewind: async (selectedIndex, timeMs) => {
        const current = simulationNavigationRef.current.simulation.state;
        if (!current) throw new Error('Simulation state is loading.');
        await simulationNavigationRef.current.simulation.rewind({
          ...createBacktestSimulationOperationRequest(current.control_revision),
          source_candle_index: simulationNavigationRef.current.replayStartIndex + selectedIndex,
          time_ms: timeMs,
        });
      },
    }
  ), [replay.controller, selectedReplayTimes]);

  const metadata = run.instrument_metadata ?? null;
  const rawPricePrecision = metadata?.price_precision ?? 5;
  const referencePrice = run.normalized_reference_price;
  const blindScale = run.blind_mode && referencePrice != null && referencePrice !== 0
    ? 100 / referencePrice
    : 1;
  const toDisplayPrice = useCallback((price: number) => (
    run.blind_mode && referencePrice != null
      ? normalizeBacktestPrice(price, referencePrice)
      : price
  ), [referencePrice, run.blind_mode]);
  const toCanonicalPrice = useCallback((price: number) => {
    if (!run.blind_mode || referencePrice == null) return price;
    const factor = 10 ** rawPricePrecision;
    return Math.round((price * referencePrice / 100) * factor) / factor;
  }, [rawPricePrecision, referencePrice, run.blind_mode]);
  const displayedPricePrecision = getBacktestDisplayPricePrecision(
    run.instrument, Boolean(run.blind_mode), referencePrice
  );
  const currentRawBar = replay.controller.getBarsUpToCursor(run.instrument, '1m').slice(-1)[0];
  const currentRawClose = currentRawBar?.close ?? null;
  const currentProtectionClose = currentRawClose == null
    ? null
    : roundPriceToPrecision(currentRawClose, rawPricePrecision);
  const currentDisplayClose = currentRawClose == null ? null : toDisplayPrice(currentRawClose);
  const simulationState = simulation.state;
  const simulationBusy = simulation.isMutating || Boolean(simulationState?.pending_operation);
  const canSimulateInstrument = Boolean(metadata?.supported_for_simulation
    && metadata.pip_size != null && metadata.contract_size != null && metadata.quote_currency);
  const entryInstrument: BacktestEntryInstrument | null = canSimulateInstrument
    ? {
      pipSize: Number(metadata?.pip_size) * Math.abs(blindScale),
      pricePrecision: displayedPricePrecision,
      contractSize: Number(metadata?.contract_size),
      quoteCurrency: String(metadata?.quote_currency ?? ''),
      quoteToUsdRate: simulationState?.current_quote_to_usd_rate ?? null,
    }
    : null;
  const currentEntryPrice = currentDisplayClose == null || !entryInstrument
    ? currentDisplayClose
    : roundPriceToPrecision(currentDisplayClose, entryInstrument.pricePrecision);
  const [entryType, setEntryType] = useState<BacktestEntryType>('market');
  const [direction, setDirection] = useState<BacktestTradeDirection>('long');
  const [entryPreviewArmed, setEntryPreviewArmed] = useState(false);
  const [previewEntryPrice, setPreviewEntryPrice] = useState<number | null>(null);
  const [previewStopLoss, setPreviewStopLoss] = useState<number | null>(null);
  const [previewTakeProfit, setPreviewTakeProfit] = useState<number | null>(null);
  const [manualLots, setManualLots] = useState<number | null>(null);
  const [autoSize, setAutoSize] = useState(true);
  const currentBalanceUsd = simulationState?.current_balance_usd ?? run.initial_balance_usd ?? 10_000;
  const riskPercent = simulationState?.risk_percent ?? run.risk_percent ?? 1;
  const currentCosts = {
    totalSpreadPips: simulationState?.cost_profile.total_spread_pips ?? 0,
    slippagePips: simulationState?.cost_profile.slippage_pips ?? 0,
    commissionUsdPerLotPerSide: simulationState?.cost_profile.commission_usd_per_lot_per_side ?? 0,
  };
  const defaultBracket = currentEntryPrice != null && entryInstrument
    ? createDefaultBacktestBracket({
      entryPrice: entryType === 'market' ? currentEntryPrice : previewEntryPrice ?? currentEntryPrice,
      direction,
      instrument: entryInstrument,
      account: { currentBalanceUsd, riskPercent },
    })
    : null;
  const activeEntryPrice = entryType === 'market'
    ? currentEntryPrice
    : previewEntryPrice ?? currentEntryPrice;
  const activeStopLoss = previewStopLoss ?? defaultBracket?.stopLossPrice ?? null;
  const activeTakeProfit = previewTakeProfit ?? defaultBracket?.takeProfitPrice ?? null;
  const sizingInput = entryInstrument && activeEntryPrice != null
    ? {
      entryType,
      direction,
      entryPrice: activeEntryPrice,
      stopLossPrice: activeStopLoss,
      takeProfitPrice: activeTakeProfit,
      instrument: entryInstrument,
      account: { currentBalanceUsd, riskPercent },
      costs: currentCosts,
      autoSize,
      manualLots,
    }
    : null;
  const sizing = sizingInput ? calculateBacktestBracketSizing(sizingInput) : null;
  const previewDraft = sizingInput && sizing ? createBacktestEntryOrderDraft(sizingInput, sizing) : null;
  const positionItems = (simulationState?.positions ?? []).flatMap((position) => {
    if (position.stop_loss_price == null || position.take_profit_price == null) return [];
    return [{
      id: position.position_id,
      side: position.side,
      remainingLots: position.remaining_lots,
      weightedEntryPrice: toDisplayPrice(position.weighted_entry_price),
      stopLossPrice: toDisplayPrice(position.stop_loss_price),
      takeProfitPrice: toDisplayPrice(position.take_profit_price),
      initialRiskUsd: position.initial_risk_usd,
      unrealizedPnlUsd: position.unrealized_pnl_usd,
      stopMoved: position.tag_ids.length > 0,
    }];
  });
  const positionRows = (simulationState?.positions ?? []).flatMap((position) => {
    if (position.stop_loss_price == null || position.take_profit_price == null) return [];
    return [{
      id: position.position_id,
      side: position.side,
      remainingLots: position.remaining_lots,
      weightedEntryPrice: position.weighted_entry_price,
      stopLossPrice: position.stop_loss_price,
      takeProfitPrice: position.take_profit_price,
      initialRiskUsd: position.initial_risk_usd,
      unrealizedPnlUsd: position.unrealized_pnl_usd,
      stopMoved: position.tag_ids.length > 0,
    }];
  });
  const workingOrders: BacktestWorkingOrder[] = (simulationState?.orders ?? [])
    .filter((order) => order.role === 'entry' && order.status === 'pending')
    .map((order) => ({
      id: order.order_id,
      side: order.side,
      orderType: order.order_type === 'limit' ? 'limit' : 'market',
      lots: order.lots,
      entryPrice: order.entry_price,
      stopLossPrice: order.stop_loss_price ?? 0,
      takeProfitPrice: order.take_profit_price ?? 0,
      projectedRiskUsd: order.projected_risk_usd ?? order.risk_budget_usd ?? 0,
    }));

  const setPreviewEntry = useCallback((price: number) => {
    setPreviewEntryPrice(price);
  }, []);
  const setPreviewStop = useCallback((price: number) => {
    setPreviewStopLoss(price);
  }, []);
  const setPreviewTarget = useCallback((price: number) => {
    setPreviewTakeProfit(price);
  }, []);
  const resetPreview = useCallback(() => {
    setEntryPreviewArmed(false);
    setPreviewEntryPrice(null);
    setPreviewStopLoss(null);
    setPreviewTakeProfit(null);
  }, []);
  const selectEntryOrder = useCallback((nextEntryType: BacktestEntryType, nextDirection: BacktestTradeDirection) => {
    if (nextEntryType !== entryType || nextDirection !== direction) {
      setPreviewEntryPrice(null);
      setPreviewStopLoss(null);
      setPreviewTakeProfit(null);
    }
    setEntryType(nextEntryType);
    setDirection(nextDirection);
    setEntryPreviewArmed(true);
  }, [direction, entryType]);

  const setProtectionCanonical = useCallback(async (positionId: string, field: 'stop_loss' | 'take_profit', value: number) => {
    const current = simulation.state;
    if (!current || simulation.isMutating) return;
    const operation = createBacktestSimulationOperationRequest(current.control_revision);
    if (field === 'stop_loss') {
      await simulation.modifyProtection(positionId, { ...operation, stop_loss: value });
    } else {
      await simulation.modifyProtection(positionId, { ...operation, take_profit: value });
    }
  }, [simulation]);
  const moveProtection = useCallback((positionId: string, field: 'stop_loss' | 'take_profit', displayedPrice: number) => (
    setProtectionCanonical(positionId, field, toCanonicalPrice(displayedPrice))
  ), [setProtectionCanonical, toCanonicalPrice]);
  const closePosition = useCallback(async (positionId: string) => {
    const current = simulation.state;
    if (!current || simulation.isMutating) return;
    await simulation.closePosition(positionId, createBacktestSimulationOperationRequest(current.control_revision));
  }, [simulation]);
  const onMoveStop = useCallback((positionId: string, price: number) => {
    ignoreRejectedMutation(moveProtection(positionId, 'stop_loss', price));
  }, [moveProtection]);
  const onMoveTarget = useCallback((positionId: string, price: number) => {
    ignoreRejectedMutation(moveProtection(positionId, 'take_profit', price));
  }, [moveProtection]);
  const onBreakEvenChart = useCallback((positionId: string, price: number) => {
    ignoreRejectedMutation(moveProtection(positionId, 'stop_loss', price));
  }, [moveProtection]);
  const onCloseChart = useCallback((positionId: string) => {
    ignoreRejectedMutation(closePosition(positionId));
  }, [closePosition]);
  const onPlaceOrder = useCallback(async (draft: BacktestEntryOrderDraft) => {
    const current = simulation.state;
    if (!current || simulationBusy || draft.stopLossPrice == null || draft.takeProfitPrice == null) return;
    const operation = createBacktestSimulationOperationRequest(current.control_revision);
    const side = draft.direction === 'long' ? 'buy' as const : 'sell' as const;
    const stop_loss = toCanonicalPrice(draft.stopLossPrice);
    const take_profit = toCanonicalPrice(draft.takeProfitPrice);
    try {
      if (draft.entryType === 'limit') {
        if (draft.entryPrice == null) return;
        const entry_price = toCanonicalPrice(draft.entryPrice);
        if (draft.autoSize) {
          await simulation.submitOrder({ ...operation, side, auto_size: true, order_type: 'limit', entry_price, stop_loss, take_profit });
        } else {
          await simulation.submitOrder({ ...operation, side, auto_size: false, lots: draft.quantityLots, order_type: 'limit', entry_price, stop_loss, take_profit });
        }
      } else {
        if (draft.autoSize) {
          await simulation.submitOrder({ ...operation, side, auto_size: true, order_type: 'market', stop_loss, take_profit });
        } else {
          await simulation.submitOrder({ ...operation, side, auto_size: false, lots: draft.quantityLots, order_type: 'market', stop_loss, take_profit });
        }
      }
      resetPreview();
    } catch {
      // The hook retains and displays the server rejection in the sidebar.
    }
  }, [resetPreview, simulation, simulationBusy, toCanonicalPrice]);

  const simulationChartUi: BacktestSimulationChartUi = {
    preview: {
      visible: Boolean(entryPreviewArmed && currentDisplayClose != null && entryInstrument && activeEntryPrice != null && activeStopLoss != null && activeTakeProfit != null),
      entryType,
      direction,
      entryPrice: activeEntryPrice ?? 0,
      stopLossPrice: activeStopLoss ?? 0,
      takeProfitPrice: activeTakeProfit ?? 0,
      pricePrecision: displayedPricePrecision,
      pipSize: entryInstrument?.pipSize ?? 0,
      quantityLots: sizing?.quantityLots ?? null,
      autoSize,
      riskBudgetUsd: sizing?.riskBudgetUsd ?? null,
      projectedRiskUsd: sizing?.projectedRiskUsd ?? null,
      projectedRewardUsd: sizing?.projectedRewardUsd ?? null,
      riskRewardRatio: sizing?.riskRewardRatio ?? null,
      currentBalanceUsd,
      canPlaceOrder: Boolean(previewDraft && !simulationBusy && simulationState?.status === 'ready'),
      orderPending: simulationBusy,
      invalidReason: sizing?.errors[0] ?? defaultBracket?.error,
      onEntryPriceChange: setPreviewEntry,
      onStopLossPriceChange: setPreviewStop,
      onTakeProfitPriceChange: setPreviewTarget,
      onPlaceOrder,
      onCancel: resetPreview,
    },
    positions: positionItems,
    currentClose: currentDisplayClose,
    pricePrecision: displayedPricePrecision,
    pipSize: entryInstrument?.pipSize ?? 0,
    disabled: simulationBusy || simulationState?.status !== 'ready',
    onMoveStop,
    onMoveTarget,
    onBreakEven: onBreakEvenChart,
    onClose: onCloseChart,
  };

  useEffect(() => () => setReplayMaximized(false), [setReplayMaximized]);

  const handleWorkspaceTabsChange = useCallback((nextTabs: BacktestChartTab[]) => {
    setTabs(nextTabs);
  }, []);
  const registerSyncChart = chartSync.registerChart;
  const registerReplayChart = replay.registerTabChart;

  const handleChartReady = useCallback((
    tabId: string,
    api: import('@getcandlekit/charts/react').ChartViewApi,
    onFollowStateChange: (isFollowing: boolean) => void
  ) => {
    const unregisterReplay = registerReplayChart(tabId, api.controller);
    const unregisterSync = registerSyncChart(tabId, api.controller, onFollowStateChange);
    return () => {
      unregisterSync();
      if (unregisterReplay) unregisterReplay();
    };
  }, [registerReplayChart, registerSyncChart]);

  const firstTimeMs = run.snapshot?.first_time_ms ?? run.coverage?.first_time_ms;
  const timezone = user?.display_timezone
    || user?.timezone
    || run.display_timezone
    || 'UTC';
  const chartOverlayStyle = {
    '--ck-bg': colors.tooltipBg,
    '--ck-fg': colors.tooltipText,
    '--ck-muted': colors.tick,
    '--ck-border': colors.tooltipBorder,
    '--ck-accent': colors.isDark ? '#60a5fa' : '#2563eb',
    '--ck-accent-fg': colors.isDark ? '#111827' : '#ffffff',
    '--ck-up': colors.isDark ? '#34d399' : '#16a34a',
    '--ck-down': colors.isDark ? '#f87171' : '#dc2626',
    '--ck-warn': colors.isDark ? '#fbbf24' : '#d97706',
  } as CSSProperties;

  return (
    <div
      className={isReplayMaximized
        ? 'backtest-candlekit backtest-replay-maximized flex h-full min-h-0 w-full max-w-none flex-col overflow-hidden'
        : 'backtest-candlekit mx-auto max-w-[1800px] space-y-4'}
      style={chartOverlayStyle}
    >
      {!isReplayMaximized && (
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="sr-only">{run.instrument} replay</h1>
            <Link to="/backtest/runs" className="text-sm font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400">
              ← Backtest runs
            </Link>
          </div>
          <button
            type="button"
            onClick={() => setReplayMaximized(true)}
            aria-label="Maximize replay chart"
            title="Maximize replay chart"
            className="rounded-md p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
          >
            <Maximize2 className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>
      )}

      {replay.status === 'loading' && (
        <section className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-5 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900" role="status">
          <Spinner />
          Loading the immutable candle snapshot and restoring the saved replay cursor…
        </section>
      )}

      {replay.status === 'error' && (
        <section className="rounded-xl border border-red-200 bg-white p-5 dark:border-red-900 dark:bg-gray-900">
          <p className="text-sm text-red-700 dark:text-red-300" role="alert">
            {replay.error ?? 'Could not load this replay.'}
          </p>
          <button
            type="button"
            onClick={replay.retryLoad}
            className="mt-3 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Retry replay load
          </button>
        </section>
      )}

      {replay.cursorSaveError && (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200" role="alert">
          {replay.cursorSaveError}
        </p>
      )}

      {simulation.status === 'error' && !simulation.state && (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200" role="alert">
          {simulation.error ?? 'Could not load the simulation state.'}
        </p>
      )}

      {replay.status === 'ready' && simulationControls && (
        <div className={[
          'backtest-simulation-layout',
          isReplayMaximized && 'backtest-simulation-layout-maximized',
          simulationSidebarCollapsed && 'backtest-simulation-layout-sidebar-collapsed',
        ].filter(Boolean).join(' ')}>
          <section className="backtest-simulation-chart-column">
            <BacktestSimulationUiProvider value={simulationChartUi}>
              <BacktestChartWorkspace
                run={run}
                maximized={isReplayMaximized}
                displayTimezone={timezone}
                initialLayout={initialLayout}
                revision={revision}
                cursorTimeMs={replay.cursorTimeMs ?? simulationState?.cursor.time_ms ?? run.replay_cursor?.time_ms ?? firstTimeMs ?? 0}
                registerDrawingFlusher={replay.registerDrawingFlusher}
                onChartReady={handleChartReady}
                snapToLive={chartSync.snapToLive}
                onTabsChange={handleWorkspaceTabsChange}
              />
            </BacktestSimulationUiProvider>
            <BacktestReplayControls
              controller={simulationControls}
              displayTimezone={timezone}
              blindMode={Boolean(run.blind_mode)}
            />
          </section>

          <aside
            className={`backtest-simulation-sidebar${simulationSidebarCollapsed ? ' is-collapsed' : ''}`}
            aria-label="Backtest simulated trading"
          >
            <button
              type="button"
              className="backtest-simulation-sidebar-toggle"
              aria-label={`${simulationSidebarCollapsed ? 'Expand' : 'Collapse'} simulated trading sidebar`}
              aria-expanded={!simulationSidebarCollapsed}
              aria-controls="backtest-simulation-sidebar-content"
              title={`${simulationSidebarCollapsed ? 'Expand' : 'Collapse'} simulated trading sidebar`}
              onClick={() => setSimulationSidebarCollapsed((collapsed) => !collapsed)}
            >
              {!simulationSidebarCollapsed && <span>Trading</span>}
              {simulationSidebarCollapsed
                ? <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                : <ChevronRight className="h-4 w-4" aria-hidden="true" />}
            </button>
            <div
              id="backtest-simulation-sidebar-content"
              className="backtest-simulation-sidebar-content"
              hidden={simulationSidebarCollapsed}
            >
              <section className="backtest-simulation-account" aria-label="Backtest account summary">
                <div><span>Starting balance</span><strong>{new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(simulationState?.initial_balance_usd ?? run.initial_balance_usd ?? 10_000)}</strong></div>
                <div><span>Current balance</span><strong>{new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(currentBalanceUsd)}</strong></div>
                <div><span>Risk per trade</span><strong>{riskPercent}%</strong></div>
                <div><span>Run status</span><strong>{simulationState?.status ?? (simulation.status === 'loading' ? 'Loading…' : run.status)}</strong></div>
              </section>

              {simulation.status === 'loading' && !simulationState && (
                <p className="text-xs text-gray-500 dark:text-gray-400" role="status">Loading committed simulation state…</p>
              )}
              {simulation.error && simulationState && (
                <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200" role="alert">{simulation.error}</p>
              )}

              {currentDisplayClose != null && entryInstrument ? (
                <BacktestEntryPanel
                  instrument={entryInstrument}
                  account={{ currentBalanceUsd, riskPercent }}
                  costs={currentCosts}
                  currentRevealedClose={currentEntryPrice ?? currentDisplayClose}
                  entryType={entryType}
                  direction={direction}
                  onOrderSelectionChange={selectEntryOrder}
                  entryPrice={entryType === 'market' ? currentEntryPrice : previewEntryPrice ?? currentEntryPrice}
                  stopLossPrice={activeStopLoss}
                  takeProfitPrice={activeTakeProfit}
                  autoSize={autoSize}
                  onAutoSizeChange={setAutoSize}
                  manualLots={manualLots}
                  onManualLotsChange={setManualLots}
                />
              ) : (
                <section className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100" role="status">
                  {metadata?.reason ?? 'Simulated order sizing is available for supported Forex instruments with frozen sizing metadata.'}
                </section>
              )}

              <BacktestOrdersAndPositions
                workingOrders={workingOrders}
                positions={positionRows}
                pricePrecision={displayedPricePrecision}
                blindMode={Boolean(run.blind_mode)}
                blindPricesAreNormalized={Boolean(run.blind_mode)}
                currentClose={currentProtectionClose}
                toDisplayPrice={toDisplayPrice}
                toCanonicalPrice={toCanonicalPrice}
                pending={simulationBusy || simulationState?.status !== 'ready'}
                onCancelOrder={(orderId) => {
                  const current = simulation.state;
                  if (current) ignoreRejectedMutation(simulation.cancelOrder(orderId, createBacktestSimulationOperationRequest(current.control_revision)));
                }}
                onMoveStop={(positionId, price) => { void setProtectionCanonical(positionId, 'stop_loss', price); }}
                onMoveTarget={(positionId, price) => { void setProtectionCanonical(positionId, 'take_profit', price); }}
                onBreakEven={(positionId, price) => { void setProtectionCanonical(positionId, 'stop_loss', price); }}
                onClosePosition={onCloseChart}
              />

              <button
                type="button"
                className="backtest-simulation-reset"
                disabled={!simulationState || simulationBusy}
                onClick={() => {
                  const current = simulation.state;
                  if (!current || !window.confirm('Reset this simulation to the first replay candle? Closed simulated trades and fills from this generation will be removed.')) return;
                  ignoreRejectedMutation(simulation.reset({
                    ...createBacktestSimulationOperationRequest(current.control_revision),
                    confirmed: true,
                  }).then(() => {
                    const firstReplayTime = selectedReplayTimes[0];
                    if (firstReplayTime != null) replay.controller.seek(firstReplayTime);
                    resetPreview();
                  }));
                }}
              >
                Reset simulation
              </button>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
