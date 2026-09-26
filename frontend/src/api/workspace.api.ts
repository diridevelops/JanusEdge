import apiClient from './client';
import type {
  UpdateWorkspaceModeRequest,
  WorkspaceModeResponse,
} from '../types/workspace.types';

/** Load the authenticated user's saved workspace, defaulting to Real on the server. */
export async function getWorkspaceMode(): Promise<WorkspaceModeResponse> {
  const response = await apiClient.get<WorkspaceModeResponse>('/workspace/mode');
  return response.data;
}

/** Persist the authenticated user's selected workspace. */
export async function updateWorkspaceMode(
  request: UpdateWorkspaceModeRequest
): Promise<WorkspaceModeResponse> {
  const response = await apiClient.put<WorkspaceModeResponse>(
    '/workspace/mode',
    request
  );
  return response.data;
}
