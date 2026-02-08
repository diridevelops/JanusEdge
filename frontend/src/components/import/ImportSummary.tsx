import { ArrowRight, CheckCircle, FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ReconstructedTrade } from '../../types/import.types';
import { formatCurrency } from '../../utils/formatters';

interface ImportSummaryProps {
  /** Number of trades imported. */
  tradeCount: number;
  /** Platform detected. */
  platform: string;
  /** File name imported. */
  fileName: string;
  /** Reconstructed trades for summary stats. */
  trades: ReconstructedTrade[];
  /** Fees applied to each trade. */
  fees: Record<number, number>;
  /** Callback to import another file. */
  onImportAnother: () => void;
}

/** Import success summary with stats and navigation. */
export function ImportSummary({
  tradeCount,
  platform,
  fileName,
  trades,
  fees,
  onImportAnother,
}: ImportSummaryProps) {
  const totalGrossPnl = trades.reduce((sum, t) => sum + t.gross_pnl, 0);
  const totalFees = Object.values(fees).reduce((sum, f) => sum + f, 0);
  const totalNetPnl = totalGrossPnl - totalFees;
  const winners = trades.filter((t) => t.gross_pnl > 0).length;
  const losers = trades.filter((t) => t.gross_pnl < 0).length;
  const breakEven = trades.filter((t) => t.gross_pnl === 0).length;

  return (
    <div className="text-center space-y-6">
      {/* Success icon */}
      <div className="flex justify-center">
        <div className="rounded-full bg-green-100 p-4">
          <CheckCircle className="h-12 w-12 text-green-600" />
        </div>
      </div>

      <div>
        <h2 className="text-xl font-semibold text-gray-900">Import Complete!</h2>
        <p className="mt-1 text-gray-500">
          Successfully imported {tradeCount} {tradeCount === 1 ? 'trade' : 'trades'} from{' '}
          {platform}
        </p>
      </div>

      {/* File info */}
      <div className="inline-flex items-center gap-2 px-4 py-2 bg-gray-50 rounded-lg text-sm text-gray-600">
        <FileText className="h-4 w-4" />
        {fileName}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-lg mx-auto">
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-gray-500 uppercase">Trades</p>
          <p className="text-lg font-semibold text-gray-900">{tradeCount}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-gray-500 uppercase">Winners</p>
          <p className="text-lg font-semibold text-green-600">{winners}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-gray-500 uppercase">Losers</p>
          <p className="text-lg font-semibold text-red-600">{losers}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-gray-500 uppercase">Break Even</p>
          <p className="text-lg font-semibold text-gray-600">{breakEven}</p>
        </div>
      </div>

      {/* P&L summary */}
      <div className="max-w-sm mx-auto bg-gray-50 rounded-lg p-4 space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-600">Gross P&L</span>
          <span className={`font-medium ${totalGrossPnl >= 0 ? 'text-profit' : 'text-loss'}`}>
            {formatCurrency(totalGrossPnl)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600">Total Fees</span>
          <span className="font-medium text-gray-900">{formatCurrency(totalFees)}</span>
        </div>
        <hr className="border-gray-200" />
        <div className="flex justify-between">
          <span className="font-medium text-gray-900">Net P&L</span>
          <span className={`font-semibold ${totalNetPnl >= 0 ? 'text-profit' : 'text-loss'}`}>
            {formatCurrency(totalNetPnl)}
          </span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-center gap-3 pt-2">
        <button onClick={onImportAnother} className="btn-secondary">
          Import Another File
        </button>
        <Link to="/trades" className="btn-primary inline-flex items-center gap-1.5">
          View Trades
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </div>
  );
}
