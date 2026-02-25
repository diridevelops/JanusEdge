import { useState } from 'react';
import type { ReconstructedTrade } from '../../types/import.types';
import { formatCurrency } from '../../utils/formatters';

interface FeeEntryTableProps {
  /** Reconstructed trades from the reconstruct step. */
  trades: ReconstructedTrade[];
  /** Current fee map: trade index → fee amount. */
  fees: Record<number, number>;
  /** Callback when a fee is changed. */
  onFeeChange: (index: number, fee: number) => void;
  /** Callback to apply bulk fee to all trades. */
  onBulkFee: (fee: number) => void;
  /** Current initial risk map: trade index → risk amount. */
  initialRisks: Record<number, number>;
  /** Callback when initial risk is changed. */
  onInitialRiskChange: (
    index: number,
    risk: number
  ) => void;
  /** Callback to apply bulk risk to all trades. */
  onBulkInitialRisk: (risk: number) => void;
}

/** Per-trade fee and risk entry table with bulk options. */
export function FeeEntryTable({
  trades,
  fees,
  onFeeChange,
  onBulkFee,
  initialRisks,
  onInitialRiskChange,
  onBulkInitialRisk,
}: FeeEntryTableProps) {
  const [bulkFee, setBulkFee] = useState('');
  const [bulkInitialRisk, setBulkInitialRisk] =
    useState('');

  function handleApplyBulk() {
    const feeVal = parseFloat(bulkFee);
    if (!isNaN(feeVal) && feeVal >= 0) {
      onBulkFee(feeVal);
    }
  }

  function handleApplyBulkRisk() {
    const riskVal = parseFloat(bulkInitialRisk);
    if (!isNaN(riskVal)) {
      onBulkInitialRisk(Math.max(0, riskVal));
    }
  }

  const totalGrossPnl = trades.reduce((sum, t) => sum + t.gross_pnl, 0);
  const totalFees = Object.values(fees).reduce((sum, f) => sum + f, 0);
  const totalInitialRisk = Object.values(
    initialRisks
  ).reduce((sum, risk) => sum + risk, 0);
  const totalNetPnl = totalGrossPnl - totalFees;

  return (
    <div className="space-y-4">
      {/* Bulk fee/risk entry */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <div>
          <label
            htmlFor="bulkFee"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Apply fee to all trades
          </label>
          <input
            id="bulkFee"
            type="number"
            min="0"
            step="0.01"
            placeholder="0.00"
            value={bulkFee}
            onChange={(e) => setBulkFee(e.target.value)}
            className="input-field w-32"
          />
        </div>
        <div className="flex items-end gap-3">
          <button
            onClick={handleApplyBulk}
            disabled={!bulkFee}
            className="btn-secondary h-[38px]"
          >
            Apply to All
          </button>
        </div>

        <div>
          <label
            htmlFor="bulkInitialRisk"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Apply initial risk to all trades
          </label>
          <input
            id="bulkInitialRisk"
            type="number"
            min="0"
            step="0.01"
            placeholder="0.00"
            value={bulkInitialRisk}
            onChange={(e) =>
              setBulkInitialRisk(e.target.value)
            }
            className="input-field w-32"
          />
        </div>
        <div className="flex items-end gap-3">
          <button
            onClick={handleApplyBulkRisk}
            disabled={!bulkInitialRisk}
            className="btn-secondary h-[38px]"
          >
            Apply to All
          </button>
        </div>
      </div>

      {/* Trade fee/risk table */}
      <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-lg">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-2.5 text-left font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                #
              </th>
              <th className="px-4 py-2.5 text-left font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                Symbol
              </th>
              <th className="px-4 py-2.5 text-left font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                Side
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                Qty
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                Entry
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                Exit
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                Gross P&L
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                Fee
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                Initial Risk
              </th>
              <th className="px-4 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider text-xs">
                Net P&L
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700 bg-white dark:bg-gray-800">
            {trades.map((trade, idx) => {
              const fee = fees[idx] ?? 0;
              const initialRisk =
                initialRisks[idx] ??
                (trade.gross_pnl - fee < 0
                  ? Math.abs(trade.gross_pnl - fee)
                  : 0);
              const netPnl = trade.gross_pnl - fee;
              return (
                <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-4 py-2 text-gray-400 dark:text-gray-500">{idx + 1}</td>
                  <td className="px-4 py-2 font-medium text-gray-900 dark:text-gray-100">
                    {trade.symbol}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                        trade.side === 'Long'
                          ? 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                          : 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                      }`}
                    >
                      {trade.side}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-gray-900 dark:text-gray-100">
                    {trade.total_quantity}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-900 dark:text-gray-100">
                    {formatCurrency(trade.avg_entry_price)}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-900 dark:text-gray-100">
                    {formatCurrency(trade.avg_exit_price)}
                  </td>
                  <td
                    className={`px-4 py-2 text-right font-medium ${
                      trade.gross_pnl >= 0 ? 'text-profit' : 'text-loss'
                    }`}
                  >
                    {formatCurrency(trade.gross_pnl)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={fee || ''}
                      placeholder="0.00"
                      onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        onFeeChange(idx, isNaN(val) ? 0 : val);
                      }}
                      className="w-24 text-right text-sm border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 rounded px-2 py-1 focus:ring-1 focus:ring-brand-500 focus:border-brand-500"
                      aria-label={`Fee for trade ${idx + 1}`}
                    />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={initialRisk || ''}
                      placeholder="0.00"
                      onChange={(e) => {
                        const val = parseFloat(
                          e.target.value
                        );
                        onInitialRiskChange(
                          idx,
                          isNaN(val)
                            ? 0
                            : Math.max(0, val)
                        );
                      }}
                      className="w-24 text-right text-sm border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 rounded px-2 py-1 focus:ring-1 focus:ring-brand-500 focus:border-brand-500"
                      aria-label={`Initial risk for trade ${idx + 1}`}
                    />
                  </td>
                  <td
                    className={`px-4 py-2 text-right font-medium ${
                      netPnl >= 0 ? 'text-profit' : 'text-loss'
                    }`}
                  >
                    {formatCurrency(netPnl)}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot className="bg-gray-50 dark:bg-gray-800 font-medium">
            <tr>
              <td colSpan={6} className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300">
                Totals:
              </td>
              <td
                className={`px-4 py-2.5 text-right ${
                  totalGrossPnl >= 0 ? 'text-profit' : 'text-loss'
                }`}
              >
                {formatCurrency(totalGrossPnl)}
              </td>
              <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300">
                {formatCurrency(totalFees)}
              </td>
              <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300">
                {formatCurrency(totalInitialRisk)}
              </td>
              <td
                className={`px-4 py-2.5 text-right ${
                  totalNetPnl >= 0 ? 'text-profit' : 'text-loss'
                }`}
              >
                {formatCurrency(totalNetPnl)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
