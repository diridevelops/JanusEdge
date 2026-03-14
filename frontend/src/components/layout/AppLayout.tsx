import { Outlet } from 'react-router-dom';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

/**
 * Main application layout with sidebar and header.
 * Renders child routes via <Outlet />.
 */
export function AppLayout() {
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
