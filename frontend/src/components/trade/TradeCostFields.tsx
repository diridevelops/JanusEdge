import { Save, X } from 'lucide-react';
import { useState } from 'react';
import { updateTrade } from '../../api/trades.api';
import { useToast } from '../../hooks/useToast';
import type { Trade } from '../../types/trade.types';
import { formatCurrency } from '../../utils/formatters';

interface TradeCostFieldsProps {
  tradeId: string;
  trade: Trade;
  onSaved?: () => void;
}

function toInputValue(value: number) {
  return value > 0 ? String(value) : '';
}

function parseNonNegativeCurrency(value: string) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

/** Editable fee and initial risk fields for a trade. */
export function TradeCostFields({ tradeId, trade, onSaved }: TradeCostFieldsProps) {
  const [fee, setFee] = useState(toInputValue(trade.fee));
  const [initialRisk, setInitialRisk] = useState(toInputValue(trade.initial_risk));
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const { addToast } = useToast();

  const origFee = toInputValue(trade.fee);
  const origInitialRisk = toInputValue(trade.initial_risk);
  const hasChanges = fee !== origFee || initialRisk !== origInitialRisk;

  async function handleSave() {
    setIsSaving(true);
    try {
      await updateTrade(tradeId, {
        fee: parseNonNegativeCurrency(fee),
        initial_risk: parseNonNegativeCurrency(initialRisk),
      });
      addToast('success', 'Fees and risk saved');
      setIsEditing(false);
      onSaved?.();
    } catch {
      addToast('error', 'Failed to save fees and risk');
    } finally {
      setIsSaving(false);
    }
  }

  function handleCancel() {
    setFee(origFee);
    setInitialRisk(origInitialRisk);
    setIsEditing(false);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
          Fees & Risk
        </h3>
        {!isEditing ? (
          <button
            onClick={() => setIsEditing(true)}
            className="text-sm text-brand-600 hover:text-brand-800"
          >
            Edit
          </button>
        ) : (
          <div className="flex gap-2">
            <button
              onClick={handleCancel}
              className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 inline-flex items-center gap-1"
            >
              <X className="h-3 w-3" />
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving || !hasChanges}
              className="text-sm text-brand-600 hover:text-brand-800 inline-flex items-center gap-1 disabled:opacity-50"
            >
              <Save className="h-3 w-3" />
              {isSaving ? 'Saving...' : 'Save'}
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Fees
          </label>
          {isEditing ? (
            <input
              type="number"
              min="0"
              step="0.01"
              value={fee}
              onChange={(event) => setFee(event.target.value)}
              placeholder="0.00"
              className="input-field text-sm"
            />
          ) : (
            <p className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700 rounded p-3">
              {formatCurrency(trade.fee)}
            </p>
          )}
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Initial Risk (No Fees)
          </label>
          {isEditing ? (
            <input
              type="number"
              min="0"
              step="0.01"
              value={initialRisk}
              onChange={(event) => setInitialRisk(event.target.value)}
              placeholder="0.00"
              className="input-field text-sm"
            />
          ) : (
            <p className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700 rounded p-3">
              {trade.initial_risk > 0 ? (
                formatCurrency(trade.initial_risk)
              ) : (
                <span className="text-gray-400 dark:text-gray-500 italic">Not set</span>
              )}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}