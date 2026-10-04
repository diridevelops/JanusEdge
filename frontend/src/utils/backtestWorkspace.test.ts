import { describe, expect, it, vi } from 'vitest';
import type {
  BacktestChartWorkspaceDocument,
  BacktestChartWorkspaceResponse,
  BacktestChartTab,
} from '../types/backtest.types';
import {
  createBacktestWorkspaceDocument,
  createBacktestWorkspacePersistence,
  fromCandleKitWorkspace,
  initializeBacktestWorkspace,
  toCandleKitWorkspace,
  type BacktestWorkspaceApi,
} from './backtestWorkspace';

const RUN_ID = '65f000000000000000000001';

function tabsFromTree(tree: unknown): Array<{ id: string; interval: number }> {
  const layout = (tree as {
    layout: { children: Array<{ children: Array<{ id: string; config: { config: { interval_minutes: number } } }> }> };
  }).layout;
  return layout.children.flatMap((tabset) => tabset.children.map((tab) => ({
    id: tab.id,
    interval: tab.config.config.interval_minutes,
  })));
}

function savedDocument(
  document = createBacktestWorkspaceDocument(RUN_ID, []),
  revision = 1
): BacktestChartWorkspaceDocument {
  return {
    ...document,
    revision,
    created_at: '2026-09-27T10:00:00+00:00',
    updated_at: '2026-09-27T10:00:00+00:00',
  };
}

describe('Backtest chart workspace conversion', () => {
  it('starts with one stable 1m chart when no legacy tabs exist', () => {
    const workspace = createBacktestWorkspaceDocument(RUN_ID, []);

    expect(tabsFromTree(workspace.tree)).toEqual([
      { id: 'chart-1', interval: 1 },
    ]);
    expect(workspace.panels['chart-1']).toEqual({
      id: 'chart-1',
      type: 'backtest-chart',
      interval_minutes: 1,
    });
  });

  it('migrates legacy chart ids and intervals into visible sibling panes', () => {
    const legacyTabs: BacktestChartTab[] = [
      { id: 'legacy-15m', position: 1, interval_minutes: 15 },
      { id: 'legacy-5m', position: 0, interval_minutes: 5 },
    ];
    const workspace = createBacktestWorkspaceDocument(RUN_ID, legacyTabs);

    expect(tabsFromTree(workspace.tree)).toEqual([
      { id: 'legacy-5m', interval: 5 },
      { id: 'legacy-15m', interval: 15 },
    ]);
    expect(workspace.panels['legacy-5m']?.interval_minutes).toBe(5);
    expect(workspace.panels['legacy-15m']?.interval_minutes).toBe(15);
  });

  it('round-trips tab ids, intervals, and FlexLayout topology', () => {
    const apiWorkspace = createBacktestWorkspaceDocument(RUN_ID, [
      { id: 'chart-left', position: 0, interval_minutes: 1 },
      { id: 'chart-right', position: 1, interval_minutes: 60 },
    ]);
    const internal = toCandleKitWorkspace(savedDocument(apiWorkspace));
    const restored = fromCandleKitWorkspace(internal);

    expect(restored.tree).toEqual(apiWorkspace.tree);
    expect(restored.panels).toEqual(apiWorkspace.panels);
    expect(tabsFromTree(restored.tree)).toEqual([
      { id: 'chart-left', interval: 1 },
      { id: 'chart-right', interval: 60 },
    ]);
  });
});

describe('Backtest workspace bootstrap and persistence', () => {
  it('saves the initial one-chart layout before returning an editable layout', async () => {
    const api: BacktestWorkspaceApi = {
      get: vi.fn().mockResolvedValue({
        workspace: null,
        revision: 0,
        legacy_tabs: [],
      } satisfies BacktestChartWorkspaceResponse),
      save: vi.fn().mockImplementation(async (_runId, request) => ({
        workspace: savedDocument(request.workspace),
        revision: 1,
        legacy_tabs: [],
      })),
    };

    const initialized = await initializeBacktestWorkspace(RUN_ID, api);

    expect(api.save).toHaveBeenCalledTimes(1);
    expect(api.save).toHaveBeenCalledWith(RUN_ID, expect.objectContaining({
      expected_revision: 0,
    }));
    expect(initialized.revision).toBe(1);
    expect(tabsFromTree(initialized.layout.tree)).toEqual([
      { id: 'chart-1', interval: 1 },
    ]);
  });

  it('loads the winning layout when another initializer wins revision zero', async () => {
    const remote = savedDocument(createBacktestWorkspaceDocument(RUN_ID, [
      { id: 'winner-chart', position: 0, interval_minutes: 30 },
    ]));
    const conflict = Object.assign(new Error('conflict'), {
      response: { status: 409 },
    });
    const api: BacktestWorkspaceApi = {
      get: vi.fn()
        .mockResolvedValueOnce({ workspace: null, revision: 0, legacy_tabs: [] })
        .mockResolvedValueOnce({ workspace: remote, revision: 1, legacy_tabs: [] }),
      save: vi.fn().mockRejectedValue(conflict),
    };

    const initialized = await initializeBacktestWorkspace(RUN_ID, api);

    expect(api.save).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(tabsFromTree(initialized.layout.tree)).toEqual([
      { id: 'winner-chart', interval: 30 },
    ]);
    expect(initialized.revision).toBe(1);
  });

  it('retains a local layout draft after a stale revision conflict', async () => {
    const draft = toCandleKitWorkspace(savedDocument(
      createBacktestWorkspaceDocument(RUN_ID, [
        { id: 'local-chart', position: 0, interval_minutes: 5 },
      ])
    ));
    const conflict = Object.assign(new Error('conflict'), {
      response: { status: 409 },
    });
    const api: BacktestWorkspaceApi = {
      get: vi.fn().mockResolvedValue({
        workspace: null,
        revision: 0,
        legacy_tabs: [],
      }),
      save: vi.fn().mockRejectedValue(conflict),
    };
    const persistence = createBacktestWorkspacePersistence(RUN_ID, 4, api);

    await expect(persistence.save(draft)).rejects.toBe(conflict);

    expect(api.save).toHaveBeenCalledTimes(1);
    expect(persistence.getConflictDraft()).toEqual(draft);
    expect(persistence.getRevision()).toBe(4);
  });
});
