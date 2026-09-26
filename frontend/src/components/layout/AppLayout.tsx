import { Outlet } from 'react-router-dom';
import { useWorkspaceMode } from '../../contexts/WorkspaceModeContext';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Spinner } from '../ui/Spinner';

/**
 * Main application layout with sidebar and header.
 * Renders child routes via <Outlet />.
 */
export function AppLayout() {
  const { isLoading, loadError, reloadWorkspaceMode } = useWorkspaceMode();

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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header />
      <Sidebar />
      <div className="ml-60">
        <main className="p-6 pt-4">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
