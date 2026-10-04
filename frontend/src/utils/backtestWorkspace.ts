import type {
  LayoutPersistence,
  PanelInstance,
  WorkspaceLayout,
  WorkspaceLayoutSummary,
} from '@getcandlekit/charts/react/workspace';
import type {
  BacktestChartTab,
  BacktestChartWorkspaceDefinition,
  BacktestChartWorkspaceDocument,
  BacktestChartWorkspaceResponse,
  BacktestChartWorkspaceSaveRequest,
} from '../types/backtest.types';

const WORKSPACE_SCHEMA_VERSION = 1 as const;
const LAYOUT_ENGINE = 'flexlayout-react' as const;
const PANEL_TYPE = 'backtest-chart' as const;

export interface BacktestWorkspaceApi {
  get(runId: string): Promise<BacktestChartWorkspaceResponse>;
  save(
    runId: string,
    request: BacktestChartWorkspaceSaveRequest
  ): Promise<BacktestChartWorkspaceResponse>;
}

function isRevisionConflict(error: unknown): boolean {
  return typeof error === 'object'
    && error !== null
    && 'response' in error
    && typeof (error as { response?: { status?: unknown } }).response === 'object'
    && (error as { response: { status?: unknown } }).response?.status === 409;
}

function tabNode(tab: BacktestChartTab, position: number) {
  const title = `Chart ${position + 1}`;
  return {
    type: 'tab',
    id: tab.id,
    name: title,
    component: PANEL_TYPE,
    config: {
      id: tab.id,
      kind: PANEL_TYPE,
      title,
      config: { interval_minutes: tab.interval_minutes },
    },
  };
}

/** Create a one-pane default or convert legacy flat tabs into sibling panes. */
export function createBacktestWorkspaceDocument(
  runId: string,
  legacyTabs: readonly BacktestChartTab[],
  now = new Date().toISOString()
): BacktestChartWorkspaceDocument {
  const orderedTabs = legacyTabs.length > 0
    ? [...legacyTabs]
      .sort((left, right) => left.position - right.position)
      .map(({ id, interval_minutes }, position) => ({
        id,
        position,
        interval_minutes,
      }))
    : [{ id: 'chart-1', position: 0, interval_minutes: 1 }];
  const weight = 100 / orderedTabs.length;
  const panels: BacktestChartWorkspaceDocument['panels'] = {};
  const children = orderedTabs.map((tab, position) => {
    panels[tab.id] = {
      id: tab.id,
      type: PANEL_TYPE,
      interval_minutes: tab.interval_minutes,
    };
    return {
      type: 'tabset',
      id: `backtest-tabset-${position + 1}`,
      weight,
      selected: 0,
      children: [tabNode(tab, position)],
    };
  });

  return {
    schema_version: WORKSPACE_SCHEMA_VERSION,
    layout_engine: LAYOUT_ENGINE,
    id: runId,
    name: 'default',
    revision: 0,
    created_at: now,
    updated_at: now,
    tree: {
      global: {
        tabEnableClose: true,
        tabEnableRename: false,
        tabSetEnableMaximize: true,
        splitterSize: 6,
        splitterExtra: 2,
        tabSetMinWidth: 120,
        tabSetMinHeight: 80,
      },
      borders: [{
        type: 'border',
        location: 'bottom',
        enableAutoHide: true,
        children: [],
      }],
      layout: {
        type: 'row',
        id: 'backtest-workspace-root',
        weight: 100,
        children,
      },
    },
    panels,
  };
}

function tabTitles(tree: unknown): Map<string, string> {
  const titles = new Map<string, string>();
  if (typeof tree !== 'object' || tree === null) return titles;

  const visit = (node: unknown) => {
    if (typeof node !== 'object' || node === null) return;
    const value = node as Record<string, unknown>;
    if (value.type === 'tab' && typeof value.id === 'string' && typeof value.name === 'string') {
      titles.set(value.id, value.name);
    }
    if (Array.isArray(value.children)) value.children.forEach(visit);
  };
  const root = tree as Record<string, unknown>;
  visit(root.layout);
  if (Array.isArray(root.borders)) root.borders.forEach(visit);
  return titles;
}

/** Translate the API document into CandleKit's versioned layout contract. */
export function toCandleKitWorkspace(
  document: BacktestChartWorkspaceDocument
): WorkspaceLayout {
  const titles = tabTitles(document.tree);
  const panels: Record<string, PanelInstance> = {};
  for (const panel of Object.values(document.panels)) {
    panels[panel.id] = {
      id: panel.id,
      kind: panel.type,
      title: titles.get(panel.id) ?? panel.id,
      config: { interval_minutes: panel.interval_minutes },
    };
  }
  return {
    version: document.schema_version,
    id: document.id,
    name: document.name,
    createdAt: document.created_at,
    updatedAt: document.updated_at,
    tree: document.tree,
    panels,
  };
}

/** Translate CandleKit's live panel metadata back to the API contract. */
export function fromCandleKitWorkspace(
  layout: WorkspaceLayout
): BacktestChartWorkspaceDefinition {
  const panels: BacktestChartWorkspaceDefinition['panels'] = {};
  for (const [panelId, panel] of Object.entries(layout.panels)) {
    const config = panel.config as Record<string, unknown>;
    panels[panelId] = {
      id: panel.id,
      type: panel.kind as typeof PANEL_TYPE,
      interval_minutes: config.interval_minutes as number,
    };
  }
  return {
    schema_version: WORKSPACE_SCHEMA_VERSION,
    layout_engine: LAYOUT_ENGINE,
    id: layout.id,
    name: 'default',
    tree: layout.tree,
    panels,
  };
}

/** Return chart metadata in the same traversal order as its dock tree. */
export function extractBacktestWorkspaceTabs(
  layout: WorkspaceLayout
): BacktestChartTab[] {
  const ids: string[] = [];
  const visit = (node: unknown) => {
    if (typeof node !== 'object' || node === null) return;
    const value = node as Record<string, unknown>;
    if (value.type === 'tab' && typeof value.id === 'string') ids.push(value.id);
    if (Array.isArray(value.children)) value.children.forEach(visit);
  };
  if (typeof layout.tree === 'object' && layout.tree !== null) {
    const tree = layout.tree as Record<string, unknown>;
    visit(tree.layout);
    if (Array.isArray(tree.borders)) tree.borders.forEach(visit);
  }
  return ids.flatMap((id, position) => {
    const panel = layout.panels[id];
    if (!panel || panel.kind !== PANEL_TYPE) return [];
    const config = panel.config as Record<string, unknown>;
    const interval = config.interval_minutes;
    if (typeof interval !== 'number') return [];
    return [{ id, position, interval_minutes: interval }];
  });
}

/** Fetch an existing workspace or revision-zero initialize/migrate it. */
export async function initializeBacktestWorkspace(
  runId: string,
  api: BacktestWorkspaceApi
): Promise<{ layout: WorkspaceLayout; revision: number }> {
  const current = await api.get(runId);
  if (current.workspace) {
    return {
      layout: toCandleKitWorkspace(current.workspace),
      revision: current.revision,
    };
  }

  const initial = createBacktestWorkspaceDocument(runId, current.legacy_tabs);
  try {
    const saved = await api.save(runId, {
      expected_revision: current.revision,
      workspace: fromDocument(initial),
    });
    if (!saved.workspace) {
      throw new Error('The initialized chart workspace was not returned by the server.');
    }
    return {
      layout: toCandleKitWorkspace(saved.workspace),
      revision: saved.revision,
    };
  } catch (error: unknown) {
    if (!isRevisionConflict(error)) throw error;
    const winner = await api.get(runId);
    if (!winner.workspace) throw error;
    return {
      layout: toCandleKitWorkspace(winner.workspace),
      revision: winner.revision,
    };
  }
}

function fromDocument(
  document: BacktestChartWorkspaceDocument
): BacktestChartWorkspaceDefinition {
  return {
    schema_version: document.schema_version,
    layout_engine: document.layout_engine,
    id: document.id,
    name: document.name,
    tree: document.tree,
    panels: document.panels,
  };
}

/**
 * CandleKit's layout storage adapter backed by the authenticated workspace API.
 * Revision conflicts stop automatic writes and retain the submitted local tree.
 */
export class BacktestWorkspacePersistence implements LayoutPersistence {
  private revision: number;
  private conflictDraft: WorkspaceLayout | null = null;

  constructor(
    private readonly runId: string,
    initialRevision: number,
    private readonly api: BacktestWorkspaceApi
  ) {
    this.revision = initialRevision;
  }

  async get(id: string): Promise<WorkspaceLayout | null> {
    if (id !== this.runId) return null;
    const response = await this.api.get(this.runId);
    this.revision = response.revision;
    return response.workspace ? toCandleKitWorkspace(response.workspace) : null;
  }

  async save(layout: WorkspaceLayout): Promise<void> {
    try {
      const response = await this.api.save(this.runId, {
        expected_revision: this.revision,
        workspace: fromCandleKitWorkspace(layout),
      });
      this.revision = response.revision;
      this.conflictDraft = null;
    } catch (error: unknown) {
      if (isRevisionConflict(error)) this.conflictDraft = structuredClone(layout);
      throw error;
    }
  }

  async list(): Promise<readonly WorkspaceLayoutSummary[]> {
    const response = await this.api.get(this.runId);
    this.revision = response.revision;
    if (!response.workspace) return [];
    return [{
      id: response.workspace.id,
      name: response.workspace.name,
      updatedAt: response.workspace.updated_at,
    }];
  }

  async delete(): Promise<void> {
    throw new Error('A Backtest chart workspace is required and cannot be deleted.');
  }

  getRevision(): number {
    return this.revision;
  }

  getConflictDraft(): WorkspaceLayout | null {
    return this.conflictDraft;
  }

  retainConflictDraft(layout: WorkspaceLayout): void {
    this.conflictDraft = structuredClone(layout);
  }

  async reloadLatest(): Promise<WorkspaceLayout | null> {
    const layout = await this.get(this.runId);
    this.conflictDraft = null;
    return layout;
  }

  async reapplyConflictDraft(): Promise<WorkspaceLayout> {
    if (!this.conflictDraft) {
      throw new Error('There is no conflicted chart workspace draft to reapply.');
    }
    const draft = this.conflictDraft;
    await this.get(this.runId);
    await this.save(draft);
    return draft;
  }
}

export function createBacktestWorkspacePersistence(
  runId: string,
  initialRevision: number,
  api: BacktestWorkspaceApi
): BacktestWorkspacePersistence {
  return new BacktestWorkspacePersistence(runId, initialRevision, api);
}
