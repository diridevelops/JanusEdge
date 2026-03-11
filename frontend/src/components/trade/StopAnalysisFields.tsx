import { Save, X } from 'lucide-react';
import { useState } from 'react';
import { listTags } from '../../api/tags.api';
import { updateTrade } from '../../api/trades.api';
import { useToast } from '../../hooks/useToast';
import type { Trade, UpdateTradeRequest } from '../../types/trade.types';
import { InfoTooltip } from '../ui/InfoTooltip';

interface StopAnalysisFieldsProps {
  tradeId: string;
  trade: Trade;
  onSaved?: () => void;
}

/**
 * Editable "Wishful stop" and "Target price" fields for stop analysis.
 * Setting a wishful stop auto-manages the wicked-out tag.
 */
export function StopAnalysisFields({ tradeId, trade, onSaved }: StopAnalysisFieldsProps) {
  const isWinningTrade = trade.net_pnl > 0;

  // Auto-default target_price to avg_exit_price for winning trades
  const defaultTarget =
    trade.target_price != null
      ? String(trade.target_price)
      : trade.net_pnl > 0
        ? String(trade.avg_exit_price)
        : '';

  const [wishStop, setWishStop] = useState(
    trade.wish_stop_price != null ? String(trade.wish_stop_price) : ''
  );
  const [targetPrice, setTargetPrice] = useState(defaultTarget);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const { addToast } = useToast();

  const origWish = trade.wish_stop_price != null ? String(trade.wish_stop_price) : '';
  const origTarget = defaultTarget;
  const hasChanges = (!isWinningTrade && wishStop !== origWish) || targetPrice !== origTarget;

  async function handleSave() {
    setIsSaving(true);
    try {
      const targetVal = targetPrice.trim() ? parseFloat(targetPrice) : null;

      const updates: UpdateTradeRequest = {
        target_price: targetVal,
      };

      if (!isWinningTrade) {
        const wishVal = wishStop.trim() ? parseFloat(wishStop) : null;

        // Auto-manage wicked-out tag
        let tagIds = [...trade.tag_ids];
        const tags = await listTags();
        const woTag = tags.find((t) => t.name === 'wicked-out');
        const woId = woTag?.id;

        if (wishVal != null) {
          // Add wicked-out tag if not present (backend will create it if needed)
          if (woId && !tagIds.includes(woId)) {
            tagIds.push(woId);
          }
        } else if (woId) {
          // Remove wicked-out tag if present
          tagIds = tagIds.filter((id) => id !== woId);
        }

        updates.wish_stop_price = wishVal;
        updates.tag_ids = tagIds;
      }

      await updateTrade(tradeId, updates);
      addToast('success', 'Stop analysis saved');
      setIsEditing(false);
      onSaved?.();
    } catch {
      addToast('error', 'Failed to save');
    } finally {
      setIsSaving(false);
    }
  }

  function handleCancel() {
    setWishStop(origWish);
    setTargetPrice(origTarget);
    setIsEditing(false);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
          Stop Analysis
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

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Wishful stop */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400 flex items-center gap-1">
              Wishful stop
              <InfoTooltip
                text="Where you wish your stop had been. If you got stopped out but the price then reversed and hit your target, enter the price that would have kept you in the trade. Used in the What-if page to analyze stop placement."
                widthClass="w-72"
              />
            </label>
            {(() => {
              const ws = isEditing ? parseFloat(wishStop) : trade.wish_stop_price;
              if (ws == null || isNaN(ws as number)) return null;
              const rDenom = Math.abs(trade.avg_entry_price - trade.avg_exit_price);
              if (rDenom === 0) return null;
              const overshootR = Math.abs(trade.avg_exit_price - ws) / rDenom;
              return (
                <span className="text-xs font-medium text-amber-600 dark:text-amber-400">
                  Overshoot = {overshootR.toFixed(2)}R
                </span>
              );
            })()}
          </div>
          {isEditing ? (
            <input
              type="number"
              step="any"
              value={wishStop}
              onChange={(e) => setWishStop(e.target.value)}
              disabled={isWinningTrade}
              placeholder="e.g. 5200.50"
              className="input-field text-sm disabled:cursor-not-allowed disabled:opacity-60"
            />
          ) : (
            <p className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700 rounded p-3">
              {origWish || <span className="text-gray-400 dark:text-gray-500 italic">Not set</span>}
            </p>
          )}
          {isWinningTrade && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Wishful stop is only editable for losing trades.
            </p>
          )}
        </div>

        {/* Target price */}
        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1 flex items-center gap-1">
            Target price
            <InfoTooltip
              text="The price you were targeting. Auto-filled from exit price for winners. Used by the what-if calculator to simulate outcomes with wider stops."
              widthClass="w-72"
            />
          </label>
          {isEditing ? (
            <input
              type="number"
              step="any"
              value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
              placeholder="e.g. 5250.00"
              className="input-field text-sm"
            />
          ) : (
            <p className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700 rounded p-3">
              {origTarget || <span className="text-gray-400 dark:text-gray-500 italic">Not set</span>}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
