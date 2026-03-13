import { BarChart3, LogOut, Moon, Sun, User } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';
import { APP_NAME, APP_TAGLINE } from '../../utils/constants';

/** Top header bar with user info and logout. */
export function Header() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-20 flex h-20 items-center justify-between gap-6 border-b border-gray-200 bg-white px-6 dark:border-gray-700 dark:bg-gray-800">
      <div className="flex min-w-0 items-center gap-3">
        <BarChart3 className="h-7 w-7 shrink-0 text-brand-600" />
        <div className="min-w-0">
          <p className="truncate text-xl font-bold text-gray-900 dark:text-gray-100">{APP_NAME}</p>
          <p className="whitespace-nowrap text-xs text-gray-500 dark:text-gray-400">{APP_TAGLINE}</p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-4">
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          className="rounded-md p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
        <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <User className="h-4 w-4" />
          <span>{user?.username}</span>
          <span className="text-gray-400 dark:text-gray-500">|</span>
          <span className="text-xs text-gray-400 dark:text-gray-500">{user?.timezone}</span>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
          aria-label="Logout"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </header>
  );
}
