import { useState } from 'react';
import { changePassword, updateDisplayTimezone, updateTimezone } from '../api/auth.api';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../hooks/useTheme';
import { useToast } from '../hooks/useToast';

const TIMEZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Phoenix',
  'America/Anchorage',
  'Pacific/Honolulu',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Paris',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Kolkata',
  'Australia/Sydney',
  'UTC',
];

/** Settings page — password change and timezone update. */
export function SettingsPage() {
  const { user, refreshProfile } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { addToast } = useToast();

  // Password change
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwLoading, setPwLoading] = useState(false);

  // Timezone
  const [timezone, setTimezone] = useState(user?.timezone ?? 'America/New_York');
  const [tzLoading, setTzLoading] = useState(false);

  // Display timezone
  const [displayTimezone, setDisplayTimezone] = useState(
    user?.display_timezone ?? user?.timezone ?? 'America/New_York'
  );
  const [dtzLoading, setDtzLoading] = useState(false);

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      addToast('error', 'New passwords do not match.');
      return;
    }
    if (newPassword.length < 6) {
      addToast('error', 'New password must be at least 6 characters.');
      return;
    }
    setPwLoading(true);
    try {
      const result = await changePassword(currentPassword, newPassword);
      addToast('success', result.message);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to change password.';
      addToast('error', message);
    } finally {
      setPwLoading(false);
    }
  }

  async function handleUpdateTimezone(e: React.FormEvent) {
    e.preventDefault();
    setTzLoading(true);
    try {
      await updateTimezone(timezone);
      addToast('success', 'Trading timezone updated successfully.');
      refreshProfile();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to update timezone.';
      addToast('error', message);
    } finally {
      setTzLoading(false);
    }
  }

  async function handleUpdateDisplayTimezone(e: React.FormEvent) {
    e.preventDefault();
    setDtzLoading(true);
    try {
      await updateDisplayTimezone(displayTimezone);
      addToast('success', 'Display timezone updated successfully.');
      refreshProfile();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to update display timezone.';
      addToast('error', message);
    } finally {
      setDtzLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Settings</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Manage your account preferences.
        </p>
      </div>

      {/* Appearance */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
          Appearance
        </h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Dark Mode</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Toggle between light and dark colour scheme.
            </p>
          </div>
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900 ${
              theme === 'dark' ? 'bg-brand-600' : 'bg-gray-200'
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                theme === 'dark' ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </div>

      {/* Profile info */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Profile</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          <div>
            <span className="text-gray-500 dark:text-gray-400">Username</span>
            <p className="font-medium text-gray-900 dark:text-gray-100">{user?.username ?? '—'}</p>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Trading Timezone</span>
            <p className="font-medium text-gray-900 dark:text-gray-100">{user?.timezone ?? '—'}</p>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Display Timezone</span>
            <p className="font-medium text-gray-900 dark:text-gray-100">{user?.display_timezone ?? '—'}</p>
          </div>
        </div>
      </div>

      {/* Change password */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
          Change Password
        </h2>
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label htmlFor="currentPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Current Password
            </label>
            <input
              id="currentPassword"
              type="password"
              className="input-field mt-1"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div>
            <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              New Password
            </label>
            <input
              id="newPassword"
              type="password"
              className="input-field mt-1"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={6}
            />
          </div>
          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Confirm New Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              className="input-field mt-1"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={6}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={pwLoading}>
            {pwLoading ? 'Changing…' : 'Change Password'}
          </button>
        </form>
      </div>

      {/* Trading Timezone */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
          Trading Timezone
        </h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          Used to interpret timestamps from platforms that don't include timezone info (e.g. NinjaTrader).
        </p>
        <form onSubmit={handleUpdateTimezone} className="space-y-4">
          <div>
            <label htmlFor="timezone" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Timezone
            </label>
            <select
              id="timezone"
              className="input-field mt-1"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn-primary" disabled={tzLoading}>
            {tzLoading ? 'Saving…' : 'Update Trading Timezone'}
          </button>
        </form>
      </div>

      {/* Display Timezone */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
          Display Timezone
        </h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          Used to display times throughout the app, including chart time axes and trade timestamps.
        </p>
        <form onSubmit={handleUpdateDisplayTimezone} className="space-y-4">
          <div>
            <label htmlFor="displayTimezone" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Timezone
            </label>
            <select
              id="displayTimezone"
              className="input-field mt-1"
              value={displayTimezone}
              onChange={(e) => setDisplayTimezone(e.target.value)}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn-primary" disabled={dtzLoading}>
            {dtzLoading ? 'Saving…' : 'Update Display Timezone'}
          </button>
        </form>
      </div>
    </div>
  );
}
