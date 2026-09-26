export interface BacktestSyncOptions {
  crosshair: boolean;
  pan: boolean;
  zoom: boolean;
}

interface BacktestSyncControlsProps {
  options: BacktestSyncOptions;
  onChange: (options: BacktestSyncOptions) => void;
}

const choices: Array<{ key: keyof BacktestSyncOptions; label: string }> = [
  { key: 'crosshair', label: 'Crosshair' },
  { key: 'pan', label: 'Pan' },
  { key: 'zoom', label: 'Zoom' },
];

/** Independent visual-sync switches; the run replay cursor remains shared. */
export function BacktestSyncControls({
  options,
  onChange,
}: BacktestSyncControlsProps) {
  return (
    <fieldset className="flex flex-wrap items-center gap-4 rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm dark:border-gray-700 dark:bg-gray-900">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Chart sync
      </legend>
      {choices.map(({ key, label }) => (
        <label key={key} className="inline-flex cursor-pointer items-center gap-2 text-gray-700 dark:text-gray-200">
          <input
            type="checkbox"
            checked={options[key]}
            onChange={(event) => onChange({ ...options, [key]: event.target.checked })}
            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800"
          />
          {label}
        </label>
      ))}
      <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
        Replay position is always shared
      </span>
    </fieldset>
  );
}
