import axios from 'axios';
import { ArrowLeft } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  createManualTrade,
  getManualTradeConversionRate,
} from '../api/trades.api';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import {
  manualTradeLotIncrement,
  manualTradeLotMinimum,
  manualTradeTickSize,
  resolveManualTradeInstrument,
} from '../utils/manualTradeInstrument';

/** Manual trade entry page. */
export function ManualTradePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { addToast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rateLookupStatus, setRateLookupStatus] = useState<
    'idle' | 'loading' | 'available' | 'unavailable'
  >('idle');
  const [rateMessage, setRateMessage] = useState('');
  const manualRateOverride = useRef(false);

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
    quote_to_usd_rate: '',
    account_name: '',
    notes: '',
  });

  const resolvedInstrument = resolveManualTradeInstrument(
    form.symbol,
    user?.symbol_mappings,
  );
  const canonicalSymbol = resolvedInstrument?.canonicalSymbol ?? '';
  const quoteCurrency = resolvedInstrument?.mapping.quote_currency?.toUpperCase() ?? '';
  const isMappedInstrument = resolvedInstrument !== null;
  const isNonUsdQuote = Boolean(
    resolvedInstrument && quoteCurrency && quoteCurrency !== 'USD',
  );
  const priceStep = resolvedInstrument?.supported
    ? String(manualTradeTickSize(resolvedInstrument))
    : '0.01';
  const lotMinimum = resolvedInstrument
    ? manualTradeLotMinimum(resolvedInstrument)
    : 1;
  const lotIncrement = resolvedInstrument
    ? manualTradeLotIncrement(resolvedInstrument)
    : 1;

  useEffect(() => {
    manualRateOverride.current = false;
    if (!isNonUsdQuote || !resolvedInstrument?.supported || !form.exit_time) {
      setRateLookupStatus('idle');
      setRateMessage('');
      setForm((previous) => (
        previous.quote_to_usd_rate
          ? { ...previous, quote_to_usd_rate: '' }
          : previous
      ));
      return undefined;
    }

    const eventDate = new Date(form.exit_time);
    if (!Number.isFinite(eventDate.getTime())) {
      setRateLookupStatus('unavailable');
      setRateMessage('Enter a valid exit time to look up the historical conversion rate.');
      setForm((previous) => ({ ...previous, quote_to_usd_rate: '' }));
      return undefined;
    }

    let active = true;
    setRateLookupStatus('loading');
    setRateMessage('Looking up the completed conversion rate at exit time…');
    setForm((previous) => ({ ...previous, quote_to_usd_rate: '' }));
    const timer = window.setTimeout(() => {
      void getManualTradeConversionRate(
        canonicalSymbol,
        eventDate.toISOString(),
      ).then((result) => {
        if (!active || manualRateOverride.current) return;
        if (result.available && result.quote_to_usd_rate != null) {
          setRateLookupStatus('available');
          const asOf = result.rate_time
            ? ` Historical rate as of ${new Date(result.rate_time).toLocaleString()}.`
            : result.quote_currency === 'USD'
              ? ' Identity conversion.'
              : ' Configured quote-unit conversion.';
          const routeLabel = result.route
            .map((leg) => leg.instrument)
            .filter(Boolean)
            .join(' → ')
            || (result.quote_currency === 'USD'
              ? 'USD identity'
              : `${result.quote_currency} unit scaling`);
          setRateMessage(`Rate loaded from ${routeLabel}.${asOf}`);
          setForm((previous) => ({
            ...previous,
            quote_to_usd_rate: String(result.quote_to_usd_rate),
          }));
        } else {
          setRateLookupStatus('unavailable');
          setRateMessage(
            result.reason || 'Historical conversion rate unavailable; enter a rate manually.',
          );
        }
      }).catch(() => {
        if (!active || manualRateOverride.current) return;
        setRateLookupStatus('unavailable');
        setRateMessage('Historical conversion rate unavailable; enter a rate manually.');
      });
    }, 300);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [
    canonicalSymbol,
    form.exit_time,
    isNonUsdQuote,
    resolvedInstrument?.supported,
  ]);

  function updateField(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (resolvedInstrument && !resolvedInstrument.supported) {
      addToast(
        'error',
        resolvedInstrument.mapping.reason
          || 'Complete this instrument’s sizing rules in Settings before creating a trade.',
      );
      return;
    }
    setIsSubmitting(true);

    try {
      const trade = await createManualTrade({
        symbol: form.symbol,
        side: form.side,
        ...(isMappedInstrument
          ? { lot_size: parseFloat(form.quantity) }
          : { total_quantity: parseFloat(form.quantity) }),
        ...(isNonUsdQuote && form.quote_to_usd_rate.trim()
          ? { quote_to_usd_rate: parseFloat(form.quote_to_usd_rate) }
          : {}),
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
    } catch (error: unknown) {
      const apiMessage = axios.isAxiosError(error)
        ? error.response?.data?.message ?? error.response?.data?.error?.message
        : null;
      const message = typeof apiMessage === 'string' && apiMessage.trim()
        ? apiMessage
        : error instanceof Error && error.message.trim()
          ? error.message
          : 'Failed to create trade';
      addToast('error', message);
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
              placeholder="e.g. NQ, ES, EUR/USD"
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

        {/* Quantity / lots */}
        <div>
          <label htmlFor="quantity" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            {isMappedInstrument ? 'Lot Size *' : 'Quantity *'}
          </label>
          <input
            id="quantity"
            type="number"
            required
            min={String(lotMinimum)}
            step={String(lotIncrement)}
            placeholder={String(lotMinimum)}
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
              step={priceStep}
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
              step={priceStep}
              placeholder="0.00"
              value={form.exit_price}
              onChange={(e) => updateField('exit_price', e.target.value)}
              className="input-field mt-1"
            />
          </div>
        </div>

        {resolvedInstrument && !resolvedInstrument.supported && (
          <p className="text-sm text-amber-600 dark:text-amber-400" role="status">
            {resolvedInstrument.mapping.reason
              || 'This Settings instrument is missing required sizing rules.'}
          </p>
        )}

        {isNonUsdQuote && (
          <div>
            <label htmlFor="quote_to_usd_rate" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              USD per 1 {quoteCurrency} *
            </label>
            <input
              id="quote_to_usd_rate"
              type="number"
              required
              min="0"
              step="any"
              placeholder="1.00"
              value={form.quote_to_usd_rate}
              onChange={(e) => {
                manualRateOverride.current = true;
                updateField('quote_to_usd_rate', e.target.value);
                setRateLookupStatus('available');
                setRateMessage('Manual conversion rate.');
              }}
              className="input-field mt-1"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400" role="status">
              {rateLookupStatus === 'loading'
                ? 'Looking up the exit-time conversion rate…'
                : rateMessage || `Enter the USD value of one ${quoteCurrency} if the historical rate is unavailable.`}
            </p>
          </div>
        )}

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
          <button
            type="submit"
            disabled={isSubmitting || rateLookupStatus === 'loading' || Boolean(resolvedInstrument && !resolvedInstrument.supported)}
            className="btn-primary"
          >
            {isSubmitting ? 'Creating...' : 'Create Trade'}
          </button>
        </div>
      </form>
    </div>
  );
}
