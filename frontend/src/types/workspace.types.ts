/** A user's active JanusEdge workspace. */
export type WorkspaceMode = 'real' | 'backtest';

/** Workspace mode persisted for the authenticated user. */
export interface WorkspaceModeResponse {
  active_mode: WorkspaceMode;
}

/** Request body used to persist the user's selected workspace. */
export interface UpdateWorkspaceModeRequest {
  active_mode: WorkspaceMode;
}
