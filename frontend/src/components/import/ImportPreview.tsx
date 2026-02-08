import type { ParsedExecution } from '../../types/import.types';
import { formatCurrency, formatDateTime } from '../../utils/formatters';

interface ImportPreviewProps {
  /** Parsed executions from upload. */
  executions: ParsedExecution[];
  /** Detected platform name. */
  platform: string;
  /** Original file name. */
  fileName: string;
  /** Total rows in CSV. */
  totalRows: number;
  /** Successfully parsed rows. */
  parsedRows: number;
}

/** Table showing parsed execution preview after CSV upload. */
export function ImportPreview({
  executions,
  platform,
  fileName,
  totalRows,
  parsedRows,
}: ImportPreviewProps) {
  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-brand-50 text-brand-700 font-medium">
          {platform}
        </span>
        <span className="text-gray-600">
          File: <span className="font-medium text-gray-900">{fileName}</span>
        </span>
        <span className="text-gray-600">
          Rows: <span className="font-medium text-gray-900">{parsedRows}</span>
          {parsedRows < totalRows && (
            <span className="text-yellow-600"> / {totalRows}</span>
          )}
        </span>
        <span className="text-gray-600">
          Executions:{' '}
          <span className="font-medium text-gray-900">{executions.length}</span>
        </span>
      </div>

      {/* Execution table */}
      <div className="overflow-x-auto border border-gray-200 rounded-lg">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2.5 text-left font-medium text-gray-500 uppercase tracking-wider text-xs">
                #
              </th>
              <th className="px-4 py-2.5 text-left font-medium text-gray-500 uppercase tracking-wider text-xs">
                Timestamp
              </th>
              <th className="px-4 py-2.5 text-left font-medium text-gray-500 uppercase tracking-wider text-xs">
                Symbol
              </th>
              <th className="px-4 py-2.5 text-left font-medium text-gray-500 uppercase tracking-wider text-xs">
                Side
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 uppercase tracking-wider text-xs">
                Qty
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 uppercase tracking-wider text-xs">
                Price
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 uppercase tracking-wider text-xs">
                Commission
              </th>
              <th className="px-4 py-2.5 text-left font-medium text-gray-500 uppercase tracking-wider text-xs">
                Account
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {executions.map((exec, idx) => (
              <tr key={idx} className="hover:bg-gray-50">
                <td className="px-4 py-2 text-gray-400">{idx + 1}</td>
                <td className="px-4 py-2 text-gray-900 whitespace-nowrap">
                  {formatDateTime(exec.timestamp)}
                </td>
                <td className="px-4 py-2 font-medium text-gray-900">
                  {exec.symbol}
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                      exec.side === 'Buy'
                        ? 'bg-green-50 text-green-700'
                        : 'bg-red-50 text-red-700'
                    }`}
                  >
                    {exec.side}
                  </span>
                </td>
                <td className="px-4 py-2 text-right text-gray-900">
                  {exec.quantity}
                </td>
                <td className="px-4 py-2 text-right text-gray-900">
                  {formatCurrency(exec.price)}
                </td>
                <td className="px-4 py-2 text-right text-gray-500">
                  {formatCurrency(exec.commission)}
                </td>
                <td className="px-4 py-2 text-gray-600 truncate max-w-[150px]">
                  {exec.account}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
