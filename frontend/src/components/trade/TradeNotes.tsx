import { Save, X } from 'lucide-react';
import { useState } from 'react';
import { updateTrade } from '../../api/trades.api';
import { useToast } from '../../hooks/useToast';

interface TradeNotesProps {
  /** Trade ID. */
  tradeId: string;
  /** Current pre-trade notes. */
  preTradeNotes: string | null;
  /** Current post-trade notes. */
  postTradeNotes: string | null;
  /** Callback after successful save. */
  onSaved?: () => void;
}

/** Editable pre-trade and post-trade notes section. */
export function TradeNotes({
  tradeId,
  preTradeNotes,
  postTradeNotes,
  onSaved,
}: TradeNotesProps) {
  const [preTrade, setPreTrade] = useState(preTradeNotes ?? '');
  const [postTrade, setPostTrade] = useState(postTradeNotes ?? '');
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const { addToast } = useToast();

  const hasChanges =
    preTrade !== (preTradeNotes ?? '') ||
    postTrade !== (postTradeNotes ?? '');

  async function handleSave() {
    setIsSaving(true);
    try {
      await updateTrade(tradeId, {
        pre_trade_notes: preTrade || null,
        post_trade_notes: postTrade || null,
      });
      addToast('success', 'Notes saved');
      setIsEditing(false);
      onSaved?.();
    } catch {
      addToast('error', 'Failed to save notes');
    } finally {
      setIsSaving(false);
    }
  }

  function handleCancel() {
    setPreTrade(preTradeNotes ?? '');
    setPostTrade(postTradeNotes ?? '');
    setIsEditing(false);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
          Trade Notes
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

      <div>
        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
          Pre-Trade Plan
        </label>
        {isEditing ? (
          <textarea
            value={preTrade}
            onChange={(e) => setPreTrade(e.target.value)}
            rows={3}
            placeholder="What was your plan before entering?"
            className="input-field text-sm"
          />
        ) : (
          <p className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700 rounded p-3 min-h-[60px] whitespace-pre-wrap">
            {preTrade || <span className="text-gray-400 dark:text-gray-500 italic">No pre-trade notes</span>}
          </p>
        )}
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
          Post-Trade Review
        </label>
        {isEditing ? (
          <textarea
            value={postTrade}
            onChange={(e) => setPostTrade(e.target.value)}
            rows={3}
            placeholder="What did you learn from this trade?"
            className="input-field text-sm"
          />
        ) : (
          <p className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700 rounded p-3 min-h-[60px] whitespace-pre-wrap">
            {postTrade || <span className="text-gray-400 dark:text-gray-500 italic">No post-trade notes</span>}
          </p>
        )}
      </div>
    </div>
  );
}
