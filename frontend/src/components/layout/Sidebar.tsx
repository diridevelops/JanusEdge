import {
  BarChart3,
  Calendar,
  FlaskConical,
  LayoutDashboard,
  List,
  Settings,
} from 'lucide-react';
import { NavLink, useLocation } from 'react-router-dom';

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/trades', label: 'Trades', icon: List },
  { to: '/calendar', label: 'Calendar', icon: Calendar },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/whatif', label: 'What-if', icon: FlaskConical },
  { to: '/settings', label: 'Settings', icon: Settings },
];

/** Sidebar navigation component. */
export function Sidebar() {
  const location = useLocation();

  return (
    <aside className="fixed bottom-0 left-0 top-20 z-10 flex w-60 flex-col border-r border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ to, label, icon: Icon }) => {
          const isTradesEntry = to === '/trades';

          return (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => {
                const showAsActive = isTradesEntry
                  ? isActive || location.pathname === '/import'
                  : isActive;

                return `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  showAsActive
                    ? 'bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-400'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-100'
                }`;
              }}
            >
              <Icon className="h-5 w-5" />
              {label}
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
