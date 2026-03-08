import { ArrowLeft } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createManualTrade } from '../api/trades.api';
import { useToast } from '../hooks/useToast';

/** Manual trade entry page. */
export function ManualTradePage() {
  const navigate = useNavigate();
  const { addToast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [form, setForm] = useState({
    symbol: '',
    side: 'Long' as 'Long' | 'Short',
    quantity: '',
    entry_price: '',
    exit_price: '',
    entry_time: '',
    exit_time: '',
    fee: '',
    initial_risk: '',
    account_name: '',
    notes: '',
  });

  function updateField(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const trade = await createManualTrade({
        symbol: form.symbol,
        side: form.side,
        total_quantity: parseFloat(form.quantity),
        entry_price: parseFloat(form.entry_price),
        exit_price: parseFloat(form.exit_price),
        entry_time: new Date(form.entry_time).toISOString(),
        exit_time: new Date(form.exit_time).toISOString(),
        fee: form.fee ? parseFloat(form.fee) : undefined,
        initial_risk: form.initial_risk
          ? parseFloat(form.initial_risk)
          : undefined,
        account: form.account_name || undefined,
        notes: form.notes || undefined,
      });
      addToast('success', 'Trade created successfully');
      navigate(`/trades/${trade.id}`);
    } catch {
      addToast('error', 'Failed to create trade');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to="/trades" className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" aria-label="Back">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">New Manual Trade</h1>
      </div>

      <form onSubmit={handleSubmit} className="card p-6 space-y-5">
        {/* Symbol & Side */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="symbol" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Symbol *
            </label>
            <input
              id="symbol"
              type="text"
              required
              placeholder="e.g. NQ, ES"
              value={form.symbol}
              onChange={(e) => updateField('symbol', e.target.value.toUpperCase())}
              className="input-field mt-1"
            />
          </div>
          <div>
            <label htmlFor="side" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Side *
            </label>
            <select
              id="side"
              value={form.side}
              onChange={(e) => updateField('side', e.target.value)}
              className="input-field mt-1"
            >
              <option value="Long">Long</option>
              <option value="Short">Short</option>
            </select>
          </div>
        </div>

        {/* Quantity */}
        <div>
          <label htmlFor="quantity" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Quantity *
          </label>
          <input
            id="quantity"
            type="number"
            required
            min="1"
            step="1"
            placeholder="1"
            value={form.quantity}
            onChange={(e) => updateField('quantity', e.target.value)}
            className="input-field mt-1"
          />
        </div>

        {/* Entry/Exit prices */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="entry_price" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Entry Price *
            </label>
            <input
              id="entry_price"
              type="number"
              required
              step="0.01"
              placeholder="0.00"
              value={form.entry_price}
              onChange={(e) => updateField('entry_price', e.target.value)}
              className="input-field mt-1"
            />
          </div>
          <div>
            <label htmlFor="exit_price" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Exit Price *
            </label>
            <input
              id="exit_price"
              type="number"
              required
              step="0.01"
              placeholder="0.00"
              value={form.exit_price}
              onChange={(e) => updateField('exit_price', e.target.value)}
              className="input-field mt-1"
            />
          </div>
        </div>

        {/* Entry/Exit times */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="entry_time" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Entry Time *
            </label>
            <input
              id="entry_time"
              type="datetime-local"
              required
              value={form.entry_time}
              onChange={(e) => updateField('entry_time', e.target.value)}
              className="input-field mt-1"
            />
          </div>
          <div>
            <label htmlFor="exit_time" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Exit Time *
            </label>
            <input
              id="exit_time"
              type="datetime-local"
              required
              value={form.exit_time}
              onChange={(e) => updateField('exit_time', e.target.value)}
              className="input-field mt-1"
            />
          </div>
        </div>

        {/* Fee, Initial Risk & Account */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label htmlFor="fee" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Fee / Commission
            </label>
            <input
              id="fee"
              type="number"
              step="0.01"
              min="0"
              placeholder="0.00"
              value={form.fee}
              onChange={(e) => updateField('fee', e.target.value)}
              className="input-field mt-1"
            />
          </div>
          <div>
            <label htmlFor="initial_risk" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Initial Risk (No Fees)
            </label>
            <input
              id="initial_risk"
              type="number"
              step="0.01"
              min="0"
              placeholder="0.00"
              value={form.initial_risk}
              onChange={(e) => updateField('initial_risk', e.target.value)}
              className="input-field mt-1"
            />
          </div>
          <div>
            <label htmlFor="account_name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Account
            </label>
            <input
              id="account_name"
              type="text"
              placeholder="e.g. SIM101"
              value={form.account_name}
              onChange={(e) => updateField('account_name', e.target.value)}
              className="input-field mt-1"
            />
          </div>
        </div>

        {/* Notes */}
        <div>
          <label htmlFor="notes" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Notes
          </label>
          <textarea
            id="notes"
            rows={3}
            placeholder="Trade notes..."
            value={form.notes}
            onChange={(e) => updateField('notes', e.target.value)}
            className="input-field mt-1"
          />
        </div>

        {/* Submit */}
        <div className="flex justify-end gap-3 pt-2">
          <Link to="/trades" className="btn-secondary">
            Cancel
          </Link>
          <button type="submit" disabled={isSubmitting} className="btn-primary">
            {isSubmitting ? 'Creating...' : 'Create Trade'}
          </button>
        </div>
      </form>
    </div>
  );
}
