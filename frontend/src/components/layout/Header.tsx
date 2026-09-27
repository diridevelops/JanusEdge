import { LogOut, Minimize2, Moon, Sun, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useWorkspaceMode } from '../../contexts/WorkspaceModeContext';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';
import { APP_NAME, APP_TAGLINE } from '../../utils/constants';
import { JanusEdgeLogo } from '../ui/JanusEdgeLogo';

/** Top header bar with user info and logout. */
interface HeaderProps {
  compact?: boolean;
  onRestoreReplay?: () => void;
}

export function Header({ compact = false, onRestoreReplay }: HeaderProps) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { activeMode, isSaving, setActiveMode } = useWorkspaceMode();

  async function handleWorkspaceChange(mode: 'real' | 'backtest') {
    if (mode === activeMode || isSaving) return;
    try {
      await setActiveMode(mode);
      navigate(mode === 'backtest' ? '/backtest/runs' : '/');
    } catch {
      // The provider displays an error and keeps the current mode selected.
    }
  }

  return (
    <header className={`sticky top-0 z-20 flex items-center justify-between border-b border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800 ${compact ? 'h-12 gap-3 px-3' : 'h-20 gap-6 px-6'}`}>
      <div className="flex min-w-0 items-center gap-3">
        <JanusEdgeLogo className={`${compact ? 'h-8 w-8' : 'h-12 w-12'} shrink-0`} aria-hidden="true" />
        <div className="min-w-0">
          <p className={`font-app-brand truncate text-gray-900 dark:text-gray-100 ${compact ? 'text-lg leading-tight' : 'text-2xl'}`}>{APP_NAME}</p>
          {!compact && (
            <p className="font-tagline-app-brand whitespace-nowrap text-xs text-gray-500 dark:text-gray-400">{APP_TAGLINE}</p>
          )}
        </div>
      </div>

      <div
        className="flex shrink-0 items-center gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-700"
        role="group"
        aria-label="Workspace"
      >
        {(['real', 'backtest'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            aria-pressed={activeMode === mode}
            disabled={isSaving}
            onClick={() => void handleWorkspaceChange(mode)}
            className={`rounded-md px-2.5 py-1.5 text-xs font-semibold capitalize transition-colors disabled:cursor-wait disabled:opacity-60 ${
              activeMode === mode
                ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-800 dark:text-gray-100'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-300 dark:hover:text-white'
            }`}
          >
            {mode === 'real' ? 'Real' : 'Backtest'}
          </button>
        ))}
      </div>

      <div className={`flex shrink-0 items-center ${compact ? 'gap-2' : 'gap-4'}`}>
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
        {onRestoreReplay && (
          <button
            type="button"
            onClick={onRestoreReplay}
            aria-label="Restore replay layout"
            title="Restore replay layout"
            className="rounded-md p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
          >
            <Minimize2 className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>
    </header>
  );
}
