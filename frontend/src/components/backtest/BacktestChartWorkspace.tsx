import {
  createWorkspace,
  FlexLayoutAdapter,
  type PanelInstance,
  type WorkspaceLayout,
} from '@getcandlekit/charts/react/workspace';
import type { ChartViewApi } from '@getcandlekit/charts/react';
import 'flexlayout-react/style/light.css';
import { createPortal } from 'react-dom';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from 'react';
import {
  getBacktestChartWorkspace,
  saveBacktestChartWorkspace,
} from '../../api/backtests.api';
import type {
  BacktestChartTab,
  BacktestRunDetail,
} from '../../types/backtest.types';
import { useChartColors } from '../../hooks/useChartColors';
import {
  createBacktestWorkspacePersistence,
  extractBacktestWorkspaceTabs,
  type BacktestWorkspaceApi,
} from '../../utils/backtestWorkspace';
import { BacktestChartTab as BacktestChartPanelView } from './BacktestChartTab';

interface BacktestChartPanelConfig extends Record<string, unknown> {
  interval_minutes: number;
}

interface BacktestChartPanelProps {
  instance: PanelInstance<BacktestChartPanelConfig>;
  updateConfig: (next: Partial<BacktestChartPanelConfig>) => void;
}

interface ChartPanelRuntime {
  runId: string;
  instrument: string;
  displayTimezone: string;
  cursorTimeMs: number;
  blindMode: boolean;
  normalizedReferencePrice: number | null;
  registerDrawingFlusher: (
    tabId: string,
    flush: () => Promise<void> | void
  ) => () => void;
  onChartReady: (
    tabId: string,
    api: ChartViewApi,
    onFollowStateChange: (isFollowing: boolean) => void
  ) => void | (() => void);
  snapToLive: (tabId: string) => void;
}

function createChartPanelComponent(
  runtimeRef: MutableRefObject<ChartPanelRuntime>
) {
  return function BacktestWorkspaceChartPanel({
    instance,
    updateConfig,
  }: BacktestChartPanelProps) {
    const runtime = runtimeRef.current;
    const interval = instance.config.interval_minutes;
    const tab: BacktestChartTab = {
      id: instance.id,
      position: 0,
      interval_minutes: interval,
    };
    return (
      <BacktestChartPanelView
        tab={tab}
        runId={runtime.runId}
        instrument={runtime.instrument}
        displayTimezone={runtime.displayTimezone}
        blindMode={runtime.blindMode}
        normalizedReferencePrice={runtime.normalizedReferencePrice}
        cursorTimeMs={runtime.cursorTimeMs}
        registerDrawingFlusher={runtime.registerDrawingFlusher}
        onIntervalChange={(_tabId, intervalMinutes) => {
          updateConfig({ interval_minutes: intervalMinutes });
        }}
        onChartReady={runtime.onChartReady}
        snapToLive={runtime.snapToLive}
      />
    );
  };
}

function isRevisionConflict(error: unknown): boolean {
  return typeof error === 'object'
    && error !== null
    && 'response' in error
    && typeof (error as { response?: { status?: unknown } }).response === 'object'
    && (error as { response: { status?: unknown } }).response?.status === 409;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return 'Could not save the chart workspace.';
}

interface BacktestChartWorkspaceProps {
  run: BacktestRunDetail;
  maximized?: boolean;
  displayTimezone: string;
  initialLayout: WorkspaceLayout;
  revision: number;
  cursorTimeMs: number;
  registerDrawingFlusher: ChartPanelRuntime['registerDrawingFlusher'];
  onChartReady: ChartPanelRuntime['onChartReady'];
  snapToLive: ChartPanelRuntime['snapToLive'];
  onTabsChange: (tabs: BacktestChartTab[]) => void;
}

interface ChartTabAddButtonPortalsProps {
  layoutRootRef: MutableRefObject<HTMLDivElement | null>;
  onAddChart: () => void;
  disabled: boolean;
}

function ChartTabAddButtonPortals({
  layoutRootRef,
  onAddChart,
  disabled,
}: ChartTabAddButtonPortalsProps) {
  const [mountNodes, setMountNodes] = useState<HTMLElement[]>([]);

  useEffect(() => {
    const root = layoutRootRef.current;
    if (!root) return;

    const createdNodes = new Set<HTMLElement>();
    let frameId = 0;

    const reconcileTabBars = () => {
      const tabBars = Array.from(
        root.querySelectorAll<HTMLElement>('.flexlayout__tabset_tabbar_inner')
      );
      const nextMountNodes = tabBars.map((tabBar) => {
        let mountNode = Array.from(tabBar.children).find((child) =>
          child.classList.contains('backtest-add-chart-tab-mount')
        ) as HTMLElement | undefined;

        if (!mountNode) {
          mountNode = document.createElement('div');
          mountNode.className = 'backtest-add-chart-tab-mount';
          mountNode.dataset.backtestAddChartMount = String(createdNodes.size + 1);
          tabBar.appendChild(mountNode);
          createdNodes.add(mountNode);
        }

        return mountNode;
      });

      setMountNodes((current) =>
        current.length === nextMountNodes.length
          && current.every((node, index) => node === nextMountNodes[index])
          ? current
          : nextMountNodes
      );
    };

    const observer = new MutationObserver(() => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(reconcileTabBars);
    });
    observer.observe(root, { childList: true, subtree: true });
    reconcileTabBars();

    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frameId);
      createdNodes.forEach((node) => node.remove());
    };
  }, [layoutRootRef]);

  return (
    <>
      {mountNodes.map((mountNode) =>
        createPortal(
          <button
            key="add-chart"
            type="button"
            onClick={() => {
              const selectedChartTab = mountNode
                .closest('.flexlayout__tabset')
                ?.querySelector<HTMLElement>(
                  '.flexlayout__tab_button--selected, .flexlayout__tab_button_stretch'
                );
              selectedChartTab?.click();
              onAddChart();
            }}
            disabled={disabled}
            aria-label="Add chart"
            title="Add chart"
            className="backtest-add-chart-tab-button"
          >
            +
          </button>,
          mountNode,
          mountNode.dataset.backtestAddChartMount
        )
      )}
    </>
  );
}

/** Persisted CandleKit/FlexLayout workspace for one ready Backtest run. */
export function BacktestChartWorkspace({
  run,
  maximized = false,
  displayTimezone,
  initialLayout,
  revision,
  cursorTimeMs,
  registerDrawingFlusher,
  onChartReady,
  snapToLive,
  onTabsChange,
}: BacktestChartWorkspaceProps) {
  const colors = useChartColors();
  const api = useMemo<BacktestWorkspaceApi>(() => ({
    get: getBacktestChartWorkspace,
    save: saveBacktestChartWorkspace,
  }), []);
  const persistence = useMemo(
    () => createBacktestWorkspacePersistence(run.id, revision, api),
    [api, revision, run.id]
  );
  const runtimeRef = useRef<ChartPanelRuntime>({
    runId: run.id,
    instrument: run.instrument,
    displayTimezone,
    blindMode: Boolean(run.blind_mode),
    normalizedReferencePrice: run.normalized_reference_price ?? null,
    cursorTimeMs,
    registerDrawingFlusher,
    onChartReady,
    snapToLive,
  });
  runtimeRef.current = {
    runId: run.id,
    instrument: run.instrument,
    displayTimezone,
    blindMode: Boolean(run.blind_mode),
    normalizedReferencePrice: run.normalized_reference_price ?? null,
    cursorTimeMs,
    registerDrawingFlusher,
    onChartReady,
    snapToLive,
  };

  const workspace = useMemo(() => {
    const manager = createWorkspace({
      id: run.id,
      storage: persistence,
      initialLayout: initialLayout.tree,
    });
    manager.importLayout(initialLayout);
    manager.registerPanel({
      kind: 'backtest-chart',
      displayName: 'Chart',
      defaultConfig: () => ({ interval_minutes: 1 }),
      component: createChartPanelComponent(runtimeRef),
    });
    return manager;
  }, [initialLayout, persistence, run.id]);

  const [isReady, setIsReady] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflictDraft, setConflictDraft] = useState<WorkspaceLayout | null>(null);
  const conflictDraftRef = useRef<WorkspaceLayout | null>(null);
  const lastValidLayoutRef = useRef<WorkspaceLayout>(initialLayout);
  const pendingLayoutRef = useRef<WorkspaceLayout | null>(null);
  const retryLayoutRef = useRef<WorkspaceLayout | null>(null);
  const savingRef = useRef(false);
  const skipNextNotificationRef = useRef(false);
  const nextChartNumberRef = useRef(extractBacktestWorkspaceTabs(initialLayout).length + 1);
  const markWorkspaceReady = useCallback(() => setIsReady(true), []);
  const workspaceRootRef = useRef<HTMLDivElement>(null);

  const enqueueSave = useCallback((layout: WorkspaceLayout) => {
    if (conflictDraftRef.current) return;
    pendingLayoutRef.current = structuredClone(layout);
    if (savingRef.current) return;
    savingRef.current = true;

    async function drain() {
      while (pendingLayoutRef.current) {
        const desired = pendingLayoutRef.current;
        pendingLayoutRef.current = null;
        try {
          await persistence.save(desired);
          retryLayoutRef.current = null;
          setSaveError(null);
        } catch (error: unknown) {
          if (isRevisionConflict(error)) {
            const draft = pendingLayoutRef.current
              ?? persistence.getConflictDraft()
              ?? desired;
            persistence.retainConflictDraft(draft);
            conflictDraftRef.current = draft;
            setConflictDraft(draft);
            pendingLayoutRef.current = null;
            break;
          }
          retryLayoutRef.current = desired;
          setSaveError(errorMessage(error));
        }
      }
      savingRef.current = false;
    }

    void drain();
  }, [persistence]);

  useEffect(() => {
    onTabsChange(extractBacktestWorkspaceTabs(initialLayout));
    const unsubscribe = workspace.subscribe((layout) => {
      if (skipNextNotificationRef.current) {
        skipNextNotificationRef.current = false;
        return;
      }
      const tabs = extractBacktestWorkspaceTabs(layout);
      if (tabs.length === 0) {
        const previous = lastValidLayoutRef.current;
        skipNextNotificationRef.current = true;
        workspace.importLayout(previous);
        onTabsChange(extractBacktestWorkspaceTabs(previous));
        setSaveError('A Backtest workspace must keep at least one chart.');
        return;
      }

      lastValidLayoutRef.current = structuredClone(layout);
      onTabsChange(tabs);
      if (conflictDraftRef.current) {
        persistence.retainConflictDraft(layout);
        conflictDraftRef.current = structuredClone(layout);
        setConflictDraft(conflictDraftRef.current);
        return;
      }
      enqueueSave(layout);
    });
    return () => {
      unsubscribe();
      pendingLayoutRef.current = null;
    };
  }, [enqueueSave, initialLayout, onTabsChange, persistence, workspace]);

  const addChart = useCallback(() => {
    const chartNumber = nextChartNumberRef.current;
    nextChartNumberRef.current += 1;
    workspace.addPanel(
      'backtest-chart',
      { interval_minutes: 1 },
      `Chart ${chartNumber}`
    );
  }, [workspace]);

  const loadRemoteLayout = useCallback(async () => {
    try {
      const remote = await persistence.reloadLatest();
      if (!remote) throw new Error('The saved Backtest workspace is unavailable.');
      conflictDraftRef.current = null;
      setConflictDraft(null);
      lastValidLayoutRef.current = remote;
      onTabsChange(extractBacktestWorkspaceTabs(remote));
      skipNextNotificationRef.current = true;
      workspace.importLayout(remote);
      setSaveError(null);
    } catch (error: unknown) {
      setSaveError(errorMessage(error));
    }
  }, [onTabsChange, persistence, workspace]);

  const reapplyLocalLayout = useCallback(async () => {
    try {
      const draft = await persistence.reapplyConflictDraft();
      conflictDraftRef.current = null;
      setConflictDraft(null);
      lastValidLayoutRef.current = draft;
      setSaveError(null);
    } catch (error: unknown) {
      conflictDraftRef.current = persistence.getConflictDraft();
      setConflictDraft(conflictDraftRef.current);
      setSaveError(errorMessage(error));
    }
  }, [persistence]);

  const retrySave = useCallback(() => {
    const failed = retryLayoutRef.current;
    if (failed) enqueueSave(failed);
  }, [enqueueSave]);

  return (
    <section className={`flex min-h-0 min-w-0 flex-col overflow-hidden bg-white dark:bg-gray-900 ${maximized ? 'h-full flex-1 rounded-none border-0' : 'h-[min(72vh,900px)] min-h-[540px] rounded-lg border border-gray-200 dark:border-gray-700'}`}>
      {conflictDraft && (
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100" role="alert">
          <span>Your local chart layout conflicts with a newer saved layout. Your draft is retained.</span>
          <button
            type="button"
            onClick={() => void loadRemoteLayout()}
            className="rounded border border-current px-2 py-1"
          >
            Load saved layout
          </button>
          <button
            type="button"
            onClick={() => void reapplyLocalLayout()}
            className="rounded bg-amber-800 px-2 py-1 text-white dark:bg-amber-200 dark:text-gray-950"
          >
            Reapply my layout
          </button>
        </div>
      )}
      {saveError && !conflictDraft && (
        <div className="flex shrink-0 items-center gap-3 border-b border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200" role="alert">
          <span>{saveError}</span>
          {retryLayoutRef.current && (
            <button type="button" onClick={retrySave} className="underline">
              Retry save
            </button>
          )}
        </div>
      )}
      <div
        ref={workspaceRootRef}
        className={`backtest-flexlayout-theme relative min-h-0 flex-1 ${conflictDraft ? 'pointer-events-none opacity-60' : ''}`}
        data-theme={colors.isDark ? 'dark' : 'light'}
      >
        <FlexLayoutAdapter
          workspace={workspace}
          className="backtest-flexlayout h-full w-full"
          hideToolbar
          onReady={markWorkspaceReady}
        />
        <ChartTabAddButtonPortals
          layoutRootRef={workspaceRootRef}
          onAddChart={addChart}
          disabled={!isReady || Boolean(conflictDraft)}
        />
      </div>
    </section>
  );
}
