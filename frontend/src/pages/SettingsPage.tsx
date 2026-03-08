import axios from 'axios';
import { useEffect, useRef, useState } from 'react';
import {
  changePassword,
  exportBackup,
  restoreBackup,
  updateDisplayTimezone,
  updateStartingEquity,
  updateTimezone,
} from '../api/auth.api';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import type { RestoreSummary } from '../types/auth.types';

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

const RESTORE_SUMMARY_ITEMS: Array<{
  key: keyof Omit<RestoreSummary, 'market_data_cache' | 'settings'>;
  label: string;
}> = [
  { key: 'accounts', label: 'Accounts' },
  { key: 'tags', label: 'Tags' },
  { key: 'import_batches', label: 'Import Batches' },
  { key: 'trades', label: 'Trades' },
  { key: 'executions', label: 'Executions' },
  { key: 'media', label: 'Media' },
];

function getErrorMessage(error: unknown, fallbackMessage: string): string {
  if (axios.isAxiosError(error)) {
    const apiMessage = error.response?.data?.message;
    if (typeof apiMessage === 'string' && apiMessage.trim()) {
      return apiMessage;
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return fallbackMessage;
}

/** Settings page — password change and timezone update. */
export function SettingsPage() {
  const { user, refreshProfile } = useAuth();
  const { addToast } = useToast();
  const restoreInputRef = useRef<HTMLInputElement | null>(null);

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

  // Starting equity
  const [startingEquity, setStartingEquity] = useState(
    String(user?.starting_equity ?? 10000)
  );
  const [seLoading, setSeLoading] = useState(false);

  // Backup / restore
  const [exportLoading, setExportLoading] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [restoreSummary, setRestoreSummary] = useState<RestoreSummary | null>(null);
  const [restoredFilename, setRestoredFilename] = useState<string>('');

  useEffect(() => {
    setTimezone(user?.timezone ?? 'America/New_York');
    setDisplayTimezone(
      user?.display_timezone ?? user?.timezone ?? 'America/New_York'
    );
    setStartingEquity(String(user?.starting_equity ?? 10000));
  }, [user?.display_timezone, user?.starting_equity, user?.timezone]);

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
      const message = getErrorMessage(err, 'Failed to change password.');
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
      await refreshProfile();
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Failed to update timezone.');
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
      await refreshProfile();
    } catch (err: unknown) {
      const message = getErrorMessage(
        err,
        'Failed to update display timezone.'
      );
      addToast('error', message);
    } finally {
      setDtzLoading(false);
    }
  }

  async function handleUpdateStartingEquity(e: React.FormEvent) {
    e.preventDefault();
    const value = parseFloat(startingEquity);
    if (isNaN(value) || value < 0) {
      addToast('error', 'Starting equity must be a non-negative number.');
      return;
    }
    setSeLoading(true);
    try {
      await updateStartingEquity(value);
      addToast('success', 'Starting equity updated successfully.');
      await refreshProfile();
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Failed to update starting equity.');
      addToast('error', message);
    } finally {
      setSeLoading(false);
    }
  }

  async function handleExportBackup() {
    setExportLoading(true);

    try {
      const { blob, filename } = await exportBackup();
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');

      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);

      addToast('success', 'Portable backup downloaded successfully.');
    } catch (err: unknown) {
      addToast('error', getErrorMessage(err, 'Failed to export backup.'));
    } finally {
      setExportLoading(false);
    }
  }

  function handleOpenRestorePicker() {
    if (restoreLoading) {
      return;
    }

    restoreInputRef.current?.click();
  }

  async function handleRestoreFileChange(
    event: React.ChangeEvent<HTMLInputElement>
  ) {
    const file = event.target.files?.[0];
    event.target.value = '';

    if (!file) {
      return;
    }

    setRestoreLoading(true);

    try {
      const result = await restoreBackup(file);
      setRestoreSummary(result.summary);
      setRestoredFilename(file.name);
      await refreshProfile();
      addToast(
        'success',
        `${result.message} Imported ${result.summary.trades.created} trades and skipped ${result.summary.trades.skipped} duplicate trades.`
      );
    } catch (err: unknown) {
      addToast('error', getErrorMessage(err, 'Failed to restore backup.'));
    } finally {
      setRestoreLoading(false);
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

      <div className="card p-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <div>
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Portable Backup
              </h2>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Export a ZIP backup of your TradeLogs data or restore one into your current account.
              </p>
            </div>
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
              Restore merges data into the current account. Existing accounts, tags, and import batches are reused when possible, and duplicate trades are skipped by a stable trade fingerprint.
            </div>
          </div>

          <div className="flex shrink-0 flex-col gap-2 sm:items-end">
            <button
              type="button"
              className="btn-secondary"
              onClick={handleExportBackup}
              disabled={exportLoading || restoreLoading}
            >
              {exportLoading ? 'Exporting…' : 'Export Backup'}
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleOpenRestorePicker}
              disabled={restoreLoading || exportLoading}
            >
              {restoreLoading ? 'Restoring…' : 'Restore Backup'}
            </button>
            <input
              ref={restoreInputRef}
              type="file"
              accept=".zip,application/zip"
              className="hidden"
              onChange={handleRestoreFileChange}
            />
          </div>
        </div>

        <div className="mt-4 text-xs text-gray-500 dark:text-gray-400">
          Choose a TradeLogs backup ZIP. Duplicate trades are detected by source, symbol, side, entry and exit times, quantity, and average prices, then skipped during restore.
        </div>

        {restoreSummary ? (
          <div className="mt-4 rounded-md border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/40">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                Last Restore Summary
              </h3>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {restoredFilename || 'Uploaded backup'}
              </span>
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {RESTORE_SUMMARY_ITEMS.map(({ key, label }) => {
                const item = restoreSummary[key];
                const secondaryLabel = 'reused' in item ? 'Reused' : 'Skipped';
                const secondaryValue = 'reused' in item ? item.reused : item.skipped;

                return (
                  <div
                    key={key}
                    className="rounded-md border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-800"
                  >
                    <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      {label}
                    </div>
                    <div className="mt-2 flex items-center justify-between text-sm text-gray-700 dark:text-gray-300">
                      <span>Created</span>
                      <span className="font-semibold text-gray-900 dark:text-gray-100">
                        {item.created}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-sm text-gray-700 dark:text-gray-300">
                      <span>{secondaryLabel}</span>
                      <span className="font-semibold text-gray-900 dark:text-gray-100">
                        {secondaryValue}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-md border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-800">
                <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Market Data Cache
                </div>
                <div className="mt-2 flex items-center justify-between text-sm text-gray-700 dark:text-gray-300">
                  <span>Upserted</span>
                  <span className="font-semibold text-gray-900 dark:text-gray-100">
                    {restoreSummary.market_data_cache.upserted}
                  </span>
                </div>
              </div>

              <div className="rounded-md border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-800">
                <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Settings Updated
                </div>
                <div className="mt-2 text-sm text-gray-700 dark:text-gray-300">
                  {restoreSummary.settings.updated.length > 0
                    ? restoreSummary.settings.updated.join(', ')
                    : 'No settings changed'}
                </div>
              </div>
            </div>
          </div>
        ) : null}
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

      {/* Starting Equity */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
          Starting Equity
        </h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          Default starting account equity used to prefill Monte Carlo simulations.
        </p>
        <form onSubmit={handleUpdateStartingEquity} className="space-y-4">
          <div>
            <label htmlFor="startingEquity" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Equity ($)
            </label>
            <input
              id="startingEquity"
              type="number"
              min="0"
              step="any"
              className="input-field mt-1"
              value={startingEquity}
              onChange={(e) => setStartingEquity(e.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={seLoading}>
            {seLoading ? 'Saving…' : 'Update Starting Equity'}
          </button>
        </form>
      </div>
    </div>
  );
}
