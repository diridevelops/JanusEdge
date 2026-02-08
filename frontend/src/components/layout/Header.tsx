import { LogOut, User } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';

/** Top header bar with user info and logout. */
export function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="sticky top-0 z-10 flex h-16 items-center justify-end gap-4 border-b border-gray-200 bg-white px-6">
      <div className="flex items-center gap-2 text-sm text-gray-600">
        <User className="h-4 w-4" />
        <span>{user?.username}</span>
        <span className="text-gray-400">|</span>
        <span className="text-xs text-gray-400">{user?.timezone}</span>
      </div>
      <button
        onClick={logout}
        className="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100 hover:text-gray-700"
        aria-label="Logout"
      >
        <LogOut className="h-4 w-4" />
        Logout
      </button>
    </header>
  );
}
