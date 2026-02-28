import { LogOut, Moon, Sun, User } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';

/** Top header bar with user info and logout. */
export function Header() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-10 flex h-16 items-center justify-end gap-4 border-b border-gray-200 bg-white px-6 dark:border-gray-700 dark:bg-gray-800">
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
    </header>
  );
}
