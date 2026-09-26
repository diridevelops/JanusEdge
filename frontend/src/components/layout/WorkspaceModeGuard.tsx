import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useWorkspaceMode } from '../../contexts/WorkspaceModeContext';
import type { WorkspaceMode } from '../../types/workspace.types';

interface WorkspaceModeGuardProps {
  requiredMode: WorkspaceMode;
  children: ReactNode;
}

/** Keep workspace-specific routes inside the user's active mode. */
export function WorkspaceModeGuard({
  requiredMode,
  children,
}: WorkspaceModeGuardProps) {
  const { activeMode, isLoading } = useWorkspaceMode();

  if (isLoading) return null;
  if (activeMode !== requiredMode) {
    return (
      <Navigate
        to={activeMode === 'backtest' ? '/backtest/runs' : '/'}
        replace
      />
    );
  }

  return <>{children}</>;
}
