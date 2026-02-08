import { useState } from 'react';
import { changePassword, updateTimezone } from '../api/auth.api';
import { useAuth } from '../hooks/useAuth';
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
  const { addToast } = useToast();

  // Password change
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwLoading, setPwLoading] = useState(false);

  // Timezone
  const [timezone, setTimezone] = useState(user?.timezone ?? 'America/New_York');
  const [tzLoading, setTzLoading] = useState(false);

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
      addToast('success', 'Timezone updated successfully.');
      refreshProfile();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to update timezone.';
      addToast('error', message);
    } finally {
      setTzLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage your account preferences.
        </p>
      </div>

      {/* Profile info */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Profile</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Username</span>
            <p className="font-medium text-gray-900">{user?.username ?? '—'}</p>
          </div>
          <div>
            <span className="text-gray-500">Timezone</span>
            <p className="font-medium text-gray-900">{user?.timezone ?? '—'}</p>
          </div>
        </div>
      </div>

      {/* Change password */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">
          Change Password
        </h2>
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label htmlFor="currentPassword" className="block text-sm font-medium text-gray-700">
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
            <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700">
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
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700">
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

      {/* Timezone */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">
          Trading Timezone
        </h2>
        <form onSubmit={handleUpdateTimezone} className="space-y-4">
          <div>
            <label htmlFor="timezone" className="block text-sm font-medium text-gray-700">
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
            {tzLoading ? 'Saving…' : 'Update Timezone'}
          </button>
        </form>
      </div>
    </div>
  );
}
