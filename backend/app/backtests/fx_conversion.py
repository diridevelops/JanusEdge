"""Quote-currency conversion helpers for immutable Backtest snapshots."""

from __future__ import annotations

import math
import re


_CONVERSION_INSTRUMENTS = {
    "EUR": ("EUR-USD", "direct"),
    "GBP": ("GBP-USD", "direct"),
    "AUD": ("AUD-USD", "direct"),
    "NZD": ("NZD-USD", "direct"),
    "JPY": ("USD-JPY", "inverse"),
    "CHF": ("USD-CHF", "inverse"),
    "CAD": ("USD-CAD", "inverse"),
    "BTC": ("BTC-USD", "direct"),
}
_BAR_MILLISECONDS = 60_000


class FXConversionUnavailable(ValueError):
    """Raised when no completed immutable conversion observation is eligible."""

    def __init__(self, quote_currency: str, event_time_ms: int):
        self.quote_currency = quote_currency
        self.event_time_ms = event_time_ms
        super().__init__(
            "No eligible completed one-minute USD conversion observation "
            f"exists for quote currency {quote_currency} at event time "
            f"{event_time_ms} ms."
        )


def quote_currency_from_instrument(instrument: str | None) -> str | None:
    """Infer a three-letter quote currency from a Dukascopy pair code."""
    if not isinstance(instrument, str):
        return None
    parts = re.split(r"[-/]", instrument.strip().upper())
    if len(parts) != 2 or any(len(part) != 3 or not part.isalpha() for part in parts):
        return None
    return parts[1]


def build_conversion_spec(quote_currency: str | None) -> dict | None:
    """Return the immutable conversion-series request for a quote currency.

    USD quotes need no downloaded series and always convert at 1. Unsupported
    non-USD currencies retain an explicit unsupported spec so event-time
    resolution can fail clearly instead of silently substituting a rate.
    """
    if quote_currency is None:
        return None
    currency = str(quote_currency).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("quote_currency must be a three-letter currency code.")
    if currency == "USD":
        return {
            "quote_currency": currency,
            "instrument": None,
            "direction": "identity",
            "supported": True,
            "completed_utc_dates": [],
        }
    instrument, direction = _CONVERSION_INSTRUMENTS.get(currency, (None, None))
    return {
        "quote_currency": currency,
        "instrument": instrument,
        "direction": direction,
        "supported": instrument is not None,
        "completed_utc_dates": [],
    }


def resolve_quote_to_usd_rate(
    quote_currency: str,
    event_time_ms: int,
    observations,
    *,
    direction: str = "direct",
) -> float:
    """Resolve USD per quote-currency unit as of a fill event.

    Conversion rows use the source candle's minute-open ``time_ms``. A row is
    eligible only when its one-minute candle has closed by ``event_time_ms``
    (``time_ms + 60_000 <= event_time_ms``). Direct rows use ``close`` as USD
    per currency unit; inverse rows use ``1 / close``. Rows after the event,
    non-finite values, and non-positive rates are ignored. The latest eligible
    valid observation is returned; absence raises ``FXConversionUnavailable``.
    USD quote currency is the identity conversion and always returns 1.
    """
    currency = str(quote_currency).strip().upper()
    if currency == "USD":
        return 1.0
    if isinstance(event_time_ms, bool) or not isinstance(event_time_ms, int):
        raise ValueError("event_time_ms must be an integer UTC epoch-millisecond value.")
    if direction not in {"direct", "inverse"}:
        raise FXConversionUnavailable(currency, event_time_ms)

    rows = observations or []
    if not isinstance(rows, (list, tuple)):
        to_records = getattr(rows, "to_dict", None)
        if not callable(to_records):
            raise TypeError("observations must be a sequence of candle mappings.")
        rows = to_records(orient="records")

    eligible = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            candle_open_ms = int(row["time_ms"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        close_time_ms = candle_open_ms + _BAR_MILLISECONDS
        if close_time_ms > event_time_ms:
            continue
        try:
            source_close = float(row["close"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(source_close) or source_close <= 0:
            continue
        rate = source_close if direction == "direct" else 1.0 / source_close
        if math.isfinite(rate) and rate > 0:
            eligible.append((close_time_ms, rate))

    if not eligible:
        raise FXConversionUnavailable(currency, event_time_ms)
    return max(eligible, key=lambda item: item[0])[1]
