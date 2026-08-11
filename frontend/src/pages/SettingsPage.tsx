import axios from 'axios';
import { Download, Plus, Settings, Trash2, Upload, X } from 'lucide-react';
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import {
  changePassword,
  exportBackup,
  restoreBackup,
  updateMarketDataMappings,
  updateDisplayTimezone,
  updateRiskBreakevenSettings,
  updateStartingEquity,
  updateSymbolMappings,
  updateTimezone,
} from '../api/auth.api';
import { createTag, createTagCategory, deleteTag, deleteTagCategory, listTagCategories, listTags, moveTag, updateTagCategory } from '../api/tags.api';
import { PageHeader } from '../components/ui/PageHeader';
import { useAuth } from '../hooks/useAuth';
import { useFilters } from '../hooks/useFilters';
import { useToast } from '../hooks/useToast';
import type {
  MarketDataMappings,
  RestoreSummary,
  SymbolMappings,
} from '../types/auth.types';
import type { Tag, TagCategory } from '../types/marketData.types';
import { APP_NAME } from '../utils/constants';

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
  key: keyof Omit<
    RestoreSummary,
    'market_data_cache' | 'market_data_datasets' | 'settings'
  >;
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
    const apiMessage = error.response?.data?.message
      ?? error.response?.data?.error?.message;
    if (typeof apiMessage === 'string' && apiMessage.trim()) {
      return apiMessage;
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return fallbackMessage;
}

interface SymbolMappingRow {
  id: string;
  baseSymbol: string;
  dollarValuePerPoint: string;
}

interface MarketDataMappingRow {
  id: string;
  sourceSymbol: string;
  targetSymbol: string;
}

const EMPTY_SYMBOL_MAPPINGS: SymbolMappings = {};
const EMPTY_MARKET_DATA_MAPPINGS: MarketDataMappings = {};
const COMPACT_INPUT_CLASS_NAME = 'input-field h-9 px-3 py-1.5 text-sm';
const MAPPINGS_TABLE_MAX_HEIGHT_CLASS = 'max-h-[20rem]';

function createRowId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function createMappingRow(
  baseSymbol = '',
  dollarValuePerPoint = ''
): SymbolMappingRow {
  return {
    id: createRowId(),
    baseSymbol,
    dollarValuePerPoint,
  };
}

function createMarketDataMappingRow(
  sourceSymbol = '',
  targetSymbol = ''
): MarketDataMappingRow {
  return {
    id: createRowId(),
    sourceSymbol,
    targetSymbol,
  };
}

function recordToMappingRows(entries: SymbolMappings): SymbolMappingRow[] {
  return Object.entries(entries).map(([baseSymbol, mapping]) =>
    createMappingRow(
      baseSymbol,
      String(mapping.dollar_value_per_point)
    )
  );
}

function updateMappingRow(
  rows: SymbolMappingRow[],
  rowId: string,
  field: 'baseSymbol' | 'dollarValuePerPoint',
  value: string
): SymbolMappingRow[] {
  return rows.map((row) => (row.id === rowId ? { ...row, [field]: value } : row));
}

function recordToMarketDataMappingRows(
  entries: MarketDataMappings
): MarketDataMappingRow[] {
  return Object.entries(entries).map(([sourceSymbol, targetSymbol]) =>
    createMarketDataMappingRow(sourceSymbol, targetSymbol)
  );
}

function updateMarketDataMappingRow(
  rows: MarketDataMappingRow[],
  rowId: string,
  field: 'sourceSymbol' | 'targetSymbol',
  value: string
): MarketDataMappingRow[] {
  return rows.map((row) => (row.id === rowId ? { ...row, [field]: value } : row));
}

function buildSymbolMappings(rows: SymbolMappingRow[]): SymbolMappings {
  const result: SymbolMappings = {};

  for (const row of rows) {
    const baseSymbol = row.baseSymbol.trim();
    const dollarValuePerPoint = row.dollarValuePerPoint.trim();

    if (!baseSymbol && !dollarValuePerPoint) {
      continue;
    }

    if (!baseSymbol || !dollarValuePerPoint) {
      throw new Error('Each symbol mapping row must include a base symbol and dollar value per point.');
    }

    const normalizedBaseSymbol = baseSymbol.toUpperCase();
    if (Object.prototype.hasOwnProperty.call(result, normalizedBaseSymbol)) {
      throw new Error(`Duplicate base symbol: ${normalizedBaseSymbol}`);
    }

    const numericDollarValuePerPoint = Number(dollarValuePerPoint);
    if (!Number.isFinite(numericDollarValuePerPoint) || numericDollarValuePerPoint <= 0) {
      throw new Error(
        `Dollar value per point must be a number greater than zero for ${normalizedBaseSymbol}.`
      );
    }

    result[normalizedBaseSymbol] = {
      dollar_value_per_point: numericDollarValuePerPoint,
    };
  }

  return result;
}

function buildMarketDataMappings(
  rows: MarketDataMappingRow[]
): MarketDataMappings {
  const result: MarketDataMappings = {};

  for (const row of rows) {
    const sourceSymbol = row.sourceSymbol.trim();
    const targetSymbol = row.targetSymbol.trim();

    if (!sourceSymbol && !targetSymbol) {
      continue;
    }

    if (!sourceSymbol || !targetSymbol) {
      throw new Error('Each market-data mapping row must include both a source symbol and a target symbol.');
    }

    const normalizedSourceSymbol = sourceSymbol.toUpperCase();
    const normalizedTargetSymbol = targetSymbol.toUpperCase();

    if (Object.prototype.hasOwnProperty.call(result, normalizedSourceSymbol)) {
      throw new Error(`Duplicate market-data source symbol: ${normalizedSourceSymbol}`);
    }

    result[normalizedSourceSymbol] = normalizedTargetSymbol;
  }

  return result;
}

/** Settings page — password change and timezone update. */
export function SettingsPage() {
  const { user, refreshProfile } = useAuth();
  const { filters, setFilters } = useFilters();
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

  // Risk-based breakeven classification
  const [riskBreakevenEnabled, setRiskBreakevenEnabled] = useState(
    user?.risk_breakeven_enabled ?? false
  );
  const [riskBreakevenRThreshold, setRiskBreakevenRThreshold] = useState(
    String(user?.risk_breakeven_r_threshold ?? 0.05)
  );
  const [riskBreakevenLoading, setRiskBreakevenLoading] = useState(false);

  // Symbol mappings
  const [symbolMappingRows, setSymbolMappingRows] = useState<SymbolMappingRow[]>([]);
  const [symbolMappingsLoading, setSymbolMappingsLoading] = useState(false);

  // Market-data mappings
  const [marketDataMappingRows, setMarketDataMappingRows] = useState<MarketDataMappingRow[]>([]);
  const [marketDataMappingsLoading, setMarketDataMappingsLoading] = useState(false);

  // Tags
  const [tags, setTags] = useState<Tag[]>([]);
  const [tagsLoading, setTagsLoading] = useState(false);
  const [deletingTagId, setDeletingTagId] = useState<string | null>(null);
  const [tagCategories, setTagCategories] = useState<TagCategory[]>([]);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [newCategoryColor, setNewCategoryColor] = useState('#6366F1');
  const [newTagNames, setNewTagNames] = useState<Record<string, string>>({});

  // Backup / restore
  const [exportLoading, setExportLoading] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [restoreSummary, setRestoreSummary] = useState<RestoreSummary | null>(null);
  const [restoredFilename, setRestoredFilename] = useState<string>('');

  const restoreMarketDataSummary =
    restoreSummary?.market_data_datasets ?? restoreSummary?.market_data_cache ?? null;

  useEffect(() => {
    setTimezone(user?.timezone ?? 'America/New_York');
    setDisplayTimezone(
      user?.display_timezone ?? user?.timezone ?? 'America/New_York'
    );
    setStartingEquity(String(user?.starting_equity ?? 10000));
    setRiskBreakevenEnabled(user?.risk_breakeven_enabled ?? false);
    setRiskBreakevenRThreshold(String(user?.risk_breakeven_r_threshold ?? 0.05));
  }, [
    user?.display_timezone,
    user?.risk_breakeven_enabled,
    user?.risk_breakeven_r_threshold,
    user?.starting_equity,
    user?.timezone,
  ]);

  useEffect(() => {
    const symbolMappings = user?.symbol_mappings ?? EMPTY_SYMBOL_MAPPINGS;
    setSymbolMappingRows(recordToMappingRows(symbolMappings));
  }, [user?.symbol_mappings]);

  useEffect(() => {
    const marketDataMappings = user?.market_data_mappings ?? EMPTY_MARKET_DATA_MAPPINGS;
    setMarketDataMappingRows(recordToMarketDataMappingRows(marketDataMappings));
  }, [user?.market_data_mappings]);

  useEffect(() => {
    if (!user?.id) {
      setTags([]);
      return;
    }
    setTagsLoading(true);
    Promise.all([listTags(), listTagCategories()])
      .then(([loadedTags, loadedCategories]) => { setTags(loadedTags); setTagCategories(loadedCategories); })
      .catch(() => addToast('error', 'Failed to load tags.'))
      .finally(() => setTagsLoading(false));
  }, [user?.id]);

  async function handleChangePassword(e: FormEvent<HTMLFormElement>) {
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

  async function handleUpdateTimezone(e: FormEvent<HTMLFormElement>) {
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

  async function handleUpdateDisplayTimezone(e: FormEvent<HTMLFormElement>) {
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

  async function handleUpdateStartingEquity(e: FormEvent<HTMLFormElement>) {
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

  async function handleUpdateRiskBreakeven(
    e: FormEvent<HTMLFormElement>
  ) {
    e.preventDefault();
    const threshold = Number(riskBreakevenRThreshold);
    if (!Number.isFinite(threshold) || threshold < 0) {
      addToast('error', 'Breakeven threshold must be a non-negative R value.');
      return;
    }
    setRiskBreakevenLoading(true);
    try {
      await updateRiskBreakevenSettings(riskBreakevenEnabled, threshold);
      addToast('success', 'Outcome classification updated successfully.');
      await refreshProfile();
    } catch (err: unknown) {
      addToast(
        'error',
        getErrorMessage(err, 'Failed to update outcome classification.')
      );
    } finally {
      setRiskBreakevenLoading(false);
    }
  }

  async function handleUpdateSymbolMappings(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    let symbolMappings: SymbolMappings;
    try {
      symbolMappings = buildSymbolMappings(symbolMappingRows);
    } catch (error: unknown) {
      addToast(
        'error',
        error instanceof Error
          ? error.message
          : 'Failed to validate symbol mappings.'
      );
      return;
    }

    setSymbolMappingsLoading(true);
    try {
      await updateSymbolMappings(symbolMappings);
      addToast('success', 'Symbol mappings updated successfully.');
      await refreshProfile();
    } catch (err: unknown) {
      addToast('error', getErrorMessage(err, 'Failed to update symbol mappings.'));
    } finally {
      setSymbolMappingsLoading(false);
    }
  }

  async function handleUpdateMarketDataMappings(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    let marketDataMappings: MarketDataMappings;
    try {
      marketDataMappings = buildMarketDataMappings(marketDataMappingRows);
    } catch (error: unknown) {
      addToast(
        'error',
        error instanceof Error
          ? error.message
          : 'Failed to validate market-data mappings.'
      );
      return;
    }

    setMarketDataMappingsLoading(true);
    try {
      await updateMarketDataMappings(marketDataMappings);
      addToast('success', 'Market-data mappings updated successfully.');
      await refreshProfile();
    } catch (err: unknown) {
      addToast('error', getErrorMessage(err, 'Failed to update market-data mappings.'));
    } finally {
      setMarketDataMappingsLoading(false);
    }
  }

  async function handleDeleteTag(tag: Tag) {
    const confirmed = window.confirm(
      `Delete tag "${tag.name}"? It will be removed from every tagged trade and cannot be restored.`
    );
    if (!confirmed) return;

    setDeletingTagId(tag.id);
    try {
      const result = await deleteTag(tag.id);
      setTags((current) => current.filter((item) => item.id !== tag.id));
      if (filters.tag === tag.id) {
        setFilters({ tag: '' });
      }
      addToast(
        'success',
        `Tag deleted and removed from ${result.trades_updated} trade${result.trades_updated === 1 ? '' : 's'}.`
      );
    } catch (err: unknown) {
      addToast('error', getErrorMessage(err, 'Failed to delete tag.'));
    } finally {
      setDeletingTagId(null);
    }
  }

  async function handleCreateCategory() {
    if (!newCategoryName.trim()) return;
    try {
      const category = await createTagCategory(newCategoryName.trim(), newCategoryColor);
      setTagCategories((current) => [...current, category]);
      setNewCategoryName('');
    } catch (err: unknown) { addToast('error', getErrorMessage(err, 'Failed to create category.')); }
  }

  async function handleMoveTag(tag: Tag, category: TagCategory) {
    if (tag.category_id === category.id) return;
    try {
      await moveTag(tag.id, category.id);
      setTags((current) => current.map((item) => item.id === tag.id ? { ...item, category_id: category.id, category_name: category.name, category_color: category.color } : item));
    } catch { addToast('error', 'Failed to move tag.'); }
  }

  async function handleCreateTagInCategory(category: TagCategory) {
    const name = newTagNames[category.id]?.trim();
    if (!name) return;
    try {
      const tag = await createTag(name, category.color, category.id);
      setTags((current) => [...current, {
        ...tag,
        category_id: category.id,
        category_name: category.name,
        category_color: category.color,
      }]);
      setNewTagNames((current) => ({ ...current, [category.id]: '' }));
    } catch (err: unknown) { addToast('error', getErrorMessage(err, 'Failed to create tag.')); }
  }

  async function handleUpdateCategory(category: TagCategory, updates: { name?: string; color?: string }) {
    try {
      const updated = await updateTagCategory(category.id, updates);
      setTagCategories((current) => current.map((item) => item.id === updated.id ? updated : item));
      setTags((current) => current.map((tag) => tag.category_id === updated.id ? { ...tag, category_name: updated.name, category_color: updated.color } : tag));
    } catch (err: unknown) { addToast('error', getErrorMessage(err, 'Failed to update category.')); }
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
    event: ChangeEvent<HTMLInputElement>
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
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        icon={Settings}
        title="Settings"
        description="Manage your account preferences."
      />

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
          Simulation Starting Equity
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

      {/* Outcome Classification */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
          Outcome Classification
        </h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          When enabled, closed trades with an absolute R multiple at or below
          the threshold are counted as breakeven. Gross-flat trades are always
          breakeven. Recorded trade P&amp;L is not changed.
        </p>
        <form onSubmit={handleUpdateRiskBreakeven} className="space-y-4">
          <div>
            <label htmlFor="riskBreakevenRThreshold" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Breakeven Threshold (R)
            </label>
            <input
              id="riskBreakevenRThreshold"
              type="number"
              min="0"
              step="0.01"
              className="input-field mt-1"
              value={riskBreakevenRThreshold}
              onChange={(event) => setRiskBreakevenRThreshold(event.target.value)}
            />
          </div>
          <label
            htmlFor="riskBreakevenEnabled"
            className="flex cursor-pointer items-start gap-3 text-sm text-gray-700 dark:text-gray-300"
          >
            <input
              id="riskBreakevenEnabled"
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
              checked={riskBreakevenEnabled}
              onChange={(event) => setRiskBreakevenEnabled(event.target.checked)}
            />
            <span>Treat trades within the R threshold as breakeven</span>
          </label>
          <button
            type="submit"
            className="btn-primary"
            disabled={riskBreakevenLoading}
          >
            {riskBreakevenLoading ? 'Savingâ€¦' : 'Update Outcome Classification'}
          </button>
        </form>
      </div>

      {/* Symbol Mappings */}
      <div className="card p-4">
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            Symbol Mappings
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Configure normalized base symbols that match imported symbols by prefix. When an imported symbol starts with a configured base symbol, {APP_NAME} uses the configured dollar value per point for analytics and trade calculations.
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Changes apply to future trade imports, stop-analysis calculations, and backup exports.
          </p>
        </div>

        <form onSubmit={handleUpdateSymbolMappings} className="mt-4 space-y-6">
          <div className="space-y-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  Base Symbol Rules
                </h3>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  A single base symbol can cover variants such as MES, MESM26, or MES 03-26 as long as the imported symbol starts with that prefix.
                </p>
              </div>
            </div>

            <div
              className={`overflow-auto rounded-lg border border-gray-200 dark:border-gray-700 ${MAPPINGS_TABLE_MAX_HEIGHT_CLASS}`}
            >
              <table className="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th className="sticky top-0 z-10 bg-gray-50 px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                      Normalized Base Symbol
                    </th>
                    <th className="sticky top-0 z-10 bg-gray-50 px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                      Dollar Value Per Point
                    </th>
                    <th className="sticky top-0 z-10 w-24 bg-gray-50 px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {symbolMappingRows.length > 0 ? (
                    symbolMappingRows.map((row) => (
                      <tr key={row.id} className="bg-white align-top dark:bg-gray-800">
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            className={COMPACT_INPUT_CLASS_NAME}
                            value={row.baseSymbol}
                            onChange={(event) => {
                              setSymbolMappingRows((current) =>
                                updateMappingRow(current, row.id, 'baseSymbol', event.target.value)
                              );
                            }}
                            placeholder="MES"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            min="0"
                            step="any"
                            className={COMPACT_INPUT_CLASS_NAME}
                            value={row.dollarValuePerPoint}
                            onChange={(event) => {
                              setSymbolMappingRows((current) =>
                                updateMappingRow(
                                  current,
                                  row.id,
                                  'dollarValuePerPoint',
                                  event.target.value
                                )
                              );
                            }}
                            placeholder="5"
                          />
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            className="inline-flex h-9 items-center gap-1.5 text-sm font-medium text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                            onClick={() => {
                              setSymbolMappingRows((current) => current.filter((item) => item.id !== row.id));
                            }}
                          >
                            <Trash2 className="h-4 w-4" aria-hidden="true" />
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr className="bg-white dark:bg-gray-800">
                      <td
                        colSpan={3}
                        className="px-3 py-4 text-xs text-gray-500 dark:text-gray-400"
                      >
                        No base symbol rules configured.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div>
              <button
                type="button"
                className="btn-secondary inline-flex items-center gap-2"
                onClick={() => setSymbolMappingRows((current) => [...current, createMappingRow()])}
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add Row
              </button>
            </div>
          </div>

          <button type="submit" className="btn-primary" disabled={symbolMappingsLoading}>
            {symbolMappingsLoading ? 'Saving…' : 'Save Symbol Mappings'}
          </button>
        </form>
      </div>

      {/* Market Data Mappings */}
      <div className="card p-4">
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            Market Data Mappings
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            By default, each symbol maps to itself. Add an explicit mapping when charts, backtesting, or related market-data features should resolve one symbol through another stored symbol.
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Example: adding MES -&gt; ES makes {APP_NAME} use ES market data for MES.
          </p>
        </div>

        <form onSubmit={handleUpdateMarketDataMappings} className="mt-4 space-y-6">
          <div
            className={`overflow-auto rounded-lg border border-gray-200 dark:border-gray-700 ${MAPPINGS_TABLE_MAX_HEIGHT_CLASS}`}
          >
            <table className="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="sticky top-0 z-10 bg-gray-50 px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                    Source Symbol
                  </th>
                  <th className="sticky top-0 z-10 bg-gray-50 px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                    Use Market Data From
                  </th>
                  <th className="sticky top-0 z-10 w-24 bg-gray-50 px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {marketDataMappingRows.length > 0 ? (
                  marketDataMappingRows.map((row) => (
                    <tr key={row.id} className="bg-white align-top dark:bg-gray-800">
                      <td className="px-3 py-2">
                        <input
                          type="text"
                          className={COMPACT_INPUT_CLASS_NAME}
                          value={row.sourceSymbol}
                          onChange={(event) => {
                            setMarketDataMappingRows((current) =>
                              updateMarketDataMappingRow(
                                current,
                                row.id,
                                'sourceSymbol',
                                event.target.value
                              )
                            );
                          }}
                          placeholder="MES"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="text"
                          className={COMPACT_INPUT_CLASS_NAME}
                          value={row.targetSymbol}
                          onChange={(event) => {
                            setMarketDataMappingRows((current) =>
                              updateMarketDataMappingRow(
                                current,
                                row.id,
                                'targetSymbol',
                                event.target.value
                              )
                            );
                          }}
                          placeholder="ES"
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          className="inline-flex h-9 items-center gap-1.5 text-sm font-medium text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                          onClick={() => {
                            setMarketDataMappingRows((current) => current.filter((item) => item.id !== row.id));
                          }}
                        >
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr className="bg-white dark:bg-gray-800">
                    <td
                      colSpan={3}
                      className="px-3 py-4 text-xs text-gray-500 dark:text-gray-400"
                    >
                      No explicit market-data mappings configured.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div>
            <button
              type="button"
              className="btn-secondary inline-flex items-center gap-2"
              onClick={() => setMarketDataMappingRows((current) => [...current, createMarketDataMappingRow()])}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add Row
            </button>
          </div>

          <button type="submit" className="btn-primary" disabled={marketDataMappingsLoading}>
            {marketDataMappingsLoading ? 'Saving…' : 'Save Market Data Mappings'}
          </button>
        </form>
      </div>

      {/* Tags */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
          Tags
        </h2>
        <div className="mt-3 flex gap-2">
          <input className="input-field h-8 text-sm" value={newCategoryName} onChange={(event) => setNewCategoryName(event.target.value)} placeholder="New category" />
          <input type="color" className="h-8 w-10 cursor-pointer rounded border border-gray-300 bg-transparent p-0.5 dark:border-gray-600" value={newCategoryColor} onChange={(event) => setNewCategoryColor(event.target.value)} aria-label="New category color" />
          <button type="button" className="btn-secondary h-8 shrink-0 whitespace-nowrap px-3 py-1 text-sm" onClick={() => void handleCreateCategory()}>Add Category</button>
        </div>
        <div className="mt-4 space-y-3">
          {tagCategories.map((category) => (
            <div key={category.id} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const tag = tags.find((item) => item.id === event.dataTransfer.getData('tag-id')); if (tag) void handleMoveTag(tag, category); }} className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
              <div className="flex items-center justify-between gap-2 text-sm font-semibold" style={{ color: category.color }}>
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <input className="input-field h-8 min-w-0 flex-1 text-sm" value={category.name} disabled={category.system_key === 'general'} onChange={(event) => setTagCategories((current) => current.map((item) => item.id === category.id ? { ...item, name: event.target.value } : item))} onBlur={(event) => { if (category.system_key !== 'general') void handleUpdateCategory(category, { name: event.target.value }); }} />
                  <input type="color" className="h-8 w-10 shrink-0 cursor-pointer rounded border border-gray-300 bg-transparent p-0.5 dark:border-gray-600" value={category.color} onChange={(event) => { const color = event.target.value; setTagCategories((current) => current.map((item) => item.id === category.id ? { ...item, color } : item)); void handleUpdateCategory(category, { color }); }} aria-label={`${category.name} category color`} />
                </div>
                {category.system_key !== 'general' && <button type="button" className="text-xs text-red-600" onClick={() => void deleteTagCategory(category.id).then(() => setTagCategories((current) => current.filter((item) => item.id !== category.id))).catch((err) => addToast('error', getErrorMessage(err, 'Move or delete all tags in this category first.')))}>Delete category</button>}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {tags.filter((tag) => tag.category_id === category.id).map((tag) => <span key={tag.id} draggable onDragStart={(event) => event.dataTransfer.setData('tag-id', tag.id)} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium" style={{ backgroundColor: `${category.color}20`, color: category.color }}>{tag.name}<button type="button" onClick={() => void handleDeleteTag(tag)}><X className="h-3 w-3" /></button></span>)}
                <button type="button" className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-400 dark:hover:bg-gray-600" onClick={() => setNewTagNames((current) => ({ ...current, [category.id]: current[category.id] ?? '' }))}><Plus className="h-3 w-3" />Add Tag</button>
              </div>
              {Object.prototype.hasOwnProperty.call(newTagNames, category.id) && <div className="mt-2 flex gap-2"><input className="input-field h-8 text-sm" value={newTagNames[category.id]} onChange={(event) => setNewTagNames((current) => ({ ...current, [category.id]: event.target.value }))} placeholder="New tag name" /><button type="button" className="btn-primary py-1 text-xs" onClick={() => void handleCreateTagInCategory(category)}>Create</button></div>}
            </div>
          ))}
        </div>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Deleting a tag removes it from every trade that uses it.
        </p>
        <div className="mt-4 hidden space-y-2">
          {tagsLoading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Loading tags…</p>
          ) : tags.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">No tags created yet.</p>
          ) : tags.map((tag) => (
            <div
              key={tag.id}
              className="flex items-center justify-between gap-3 rounded-md border border-gray-200 px-3 py-2 dark:border-gray-700"
            >
              <div className="flex items-center gap-2 text-sm text-gray-900 dark:text-gray-100">
                <span
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: tag.color }}
                  aria-hidden="true"
                />
                {tag.name}
              </div>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 text-sm font-medium text-red-600 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-60 dark:text-red-400 dark:hover:text-red-300"
                onClick={() => void handleDeleteTag(tag)}
                disabled={deletingTagId !== null}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                {deletingTagId === tag.id ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Backup */}
      <div className="card p-4">
        <div className="space-y-2">
          <div>
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
              Backup
            </h2>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Export a ZIP backup of your {APP_NAME} data or restore one into your current account.
            </p>
          </div>
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            Restore merges data into the current account. Existing accounts, tags, and import batches are reused when possible, and duplicate trades are skipped.
          </div>
        </div>

        <div className="mt-4 text-xs text-gray-500 dark:text-gray-400">
          Choose a {APP_NAME} backup ZIP. Duplicate trades are detected by source, symbol, side, entry and exit times, quantity, and average prices, then skipped during restore.
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
                  Market Data
                </div>
                <div className="mt-2 flex items-center justify-between text-sm text-gray-700 dark:text-gray-300">
                  <span>Upserted</span>
                  <span className="font-semibold text-gray-900 dark:text-gray-100">
                    {restoreMarketDataSummary?.upserted ?? 0}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between text-sm text-gray-700 dark:text-gray-300">
                  <span>Objects Restored</span>
                  <span className="font-semibold text-gray-900 dark:text-gray-100">
                    {restoreMarketDataSummary?.objects_restored ?? 0}
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

        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-gray-200 pt-4 dark:border-gray-700">
          <button
            type="button"
            className="btn-primary gap-2"
            onClick={handleExportBackup}
            disabled={exportLoading || restoreLoading}
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            <span>{exportLoading ? 'Exporting…' : 'Export Backup'}</span>
          </button>
          <button
            type="button"
            className="btn-secondary gap-2"
            onClick={handleOpenRestorePicker}
            disabled={restoreLoading || exportLoading}
          >
            <Upload className="h-4 w-4" aria-hidden="true" />
            <span>{restoreLoading ? 'Restoring…' : 'Restore Backup'}</span>
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
    </div>
  );
}
