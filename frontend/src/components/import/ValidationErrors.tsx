import { AlertTriangle, X } from 'lucide-react';
import type { ParseError } from '../../types/import.types';

interface ValidationErrorsProps {
  /** List of row-level parse errors. */
  errors: ParseError[];
  /** Callback to dismiss the errors panel. */
  onDismiss?: () => void;
}

/** Displays row-level CSV parse errors. */
export function ValidationErrors({ errors, onDismiss }: ValidationErrorsProps) {
  if (errors.length === 0) return null;

  return (
    <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0" />
          <h3 className="text-sm font-medium text-yellow-800 dark:text-yellow-300">
            {errors.length} parsing {errors.length === 1 ? 'error' : 'errors'} found
          </h3>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-yellow-600 dark:text-yellow-400 hover:text-yellow-800 dark:hover:text-yellow-200"
            aria-label="Dismiss errors"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className="mt-3 max-h-48 overflow-y-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-yellow-700 dark:text-yellow-400 uppercase">
              <th className="pr-4 pb-1">Row</th>
              <th className="pr-4 pb-1">Field</th>
              <th className="pb-1">Issue</th>
            </tr>
          </thead>
          <tbody className="text-yellow-800 dark:text-yellow-300">
            {errors.map((err, idx) => (
              <tr key={idx}>
                <td className="pr-4 py-0.5">{err.row}</td>
                <td className="pr-4 py-0.5 font-mono text-xs">{err.field}</td>
                <td className="py-0.5">{err.issue}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
