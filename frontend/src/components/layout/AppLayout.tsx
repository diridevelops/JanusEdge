import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { useWorkspaceMode } from '../../contexts/WorkspaceModeContext';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Spinner } from '../ui/Spinner';

export interface AppLayoutOutletContext {
  isReplayMaximized: boolean;
  setReplayMaximized: (maximized: boolean) => void;
}

/**
 * Main application layout with sidebar and header.
 * Renders child routes via <Outlet />.
 */
export function AppLayout() {
  const { isLoading, loadError, reloadWorkspaceMode } = useWorkspaceMode();
  const [isReplayMaximized, setReplayMaximized] = useState(false);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <Spinner size="lg" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-gray-50 px-6 text-center dark:bg-gray-900">
        <p role="alert" className="max-w-md text-sm text-gray-700 dark:text-gray-300">
          Could not load your saved workspace. Retry before opening workspace data.
        </p>
        <button
          type="button"
          onClick={reloadWorkspaceMode}
          className="btn-primary"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className={`${isReplayMaximized ? 'h-dvh overflow-hidden' : 'min-h-screen'} bg-gray-50 dark:bg-gray-900`}>
      <Header
        compact={isReplayMaximized}
        onRestoreReplay={isReplayMaximized ? () => setReplayMaximized(false) : undefined}
      />
      {!isReplayMaximized && <Sidebar />}
      <div className={isReplayMaximized ? 'h-[calc(100dvh-3rem)] w-full' : 'ml-60'}>
        <main className={isReplayMaximized ? 'h-full min-h-0 overflow-hidden p-0' : 'p-6 pt-4'}>
          <Outlet context={{ isReplayMaximized, setReplayMaximized } satisfies AppLayoutOutletContext} />
        </main>
      </div>
    </div>
  );
}
