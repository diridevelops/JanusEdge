import { useAuth } from '../../hooks/useAuth';
import type { Execution } from '../../types/execution.types';
import { formatCurrency, formatDateTime } from '../../utils/formatters';

interface ExecutionListProps {
  /** Executions for one trade. */
  executions: Execution[];
}

/** Execution table for trade detail page. */
export function ExecutionList({ executions }: ExecutionListProps) {
  const { user } = useAuth();
  if (executions.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-4">No executions available.</p>
    );
  }

  return (
    <div className="overflow-x-auto border border-gray-200 rounded-lg">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-2 text-left font-medium text-gray-500 uppercase tracking-wider text-xs">
              #
            </th>
            <th className="px-4 py-2 text-left font-medium text-gray-500 uppercase tracking-wider text-xs">
              Timestamp
            </th>
            <th className="px-4 py-2 text-left font-medium text-gray-500 uppercase tracking-wider text-xs">
              Side
            </th>
            <th className="px-4 py-2 text-right font-medium text-gray-500 uppercase tracking-wider text-xs">
              Qty
            </th>
            <th className="px-4 py-2 text-right font-medium text-gray-500 uppercase tracking-wider text-xs">
              Price
            </th>
            <th className="px-4 py-2 text-right font-medium text-gray-500 uppercase tracking-wider text-xs">
              Commission
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {executions.map((exec, idx) => (
            <tr key={exec.id || idx} className="hover:bg-gray-50">
              <td className="px-4 py-2 text-gray-400">{idx + 1}</td>
              <td className="px-4 py-2 text-gray-900 whitespace-nowrap">
                {formatDateTime(exec.timestamp, user?.display_timezone)}
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
