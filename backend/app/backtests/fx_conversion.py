"""Quote-currency conversion helpers for immutable Backtest snapshots."""

from __future__ import annotations

from collections import deque
import math
import re


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


def build_conversion_spec(
    quote_currency: str | None,
    *,
    instruments=None,
    quote_currency_unit_scale: float | None = None,
) -> dict | None:
    """Freeze the shortest available instrument route from quote currency to USD."""
    if quote_currency is None:
        return None
    currency = str(quote_currency).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("quote_currency must be a three-letter currency code.")
    conversion_currency, unit_scale = _MINOR_CURRENCY_UNITS.get(
        currency, (currency, 1.0)
    )
    if quote_currency_unit_scale is not None:
        try:
            unit_scale = float(quote_currency_unit_scale)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("quote_currency_unit_scale must be positive and finite.") from exc
        if not math.isfinite(unit_scale) or unit_scale <= 0:
            raise ValueError("quote_currency_unit_scale must be positive and finite.")
    if instruments is None:
        try:
            from app.market_data.symbol_mapper import get_default_instrument_mappings

            instruments = get_default_instrument_mappings()
        except (ImportError, OSError, RuntimeError):
            instruments = {}
    route = _shortest_conversion_route(conversion_currency, instruments)
    if conversion_currency == "USD":
        route = []
        supported = True
    else:
        supported = route is not None
        route = route or []
    # Preserve the legacy one-pair fields for readers of old preparation jobs.
    first = route[0] if len(route) == 1 else None
    return {
        "quote_currency": currency,
        "conversion_currency": conversion_currency,
        "quote_currency_unit_scale": unit_scale,
        "instrument": first["instrument"] if first else None,
        "direction": first["direction"] if first else "identity" if not route else None,
        "route": route,
        "supported": supported,
        "reason": None if supported else (
            f"No currency-pair route from {currency} to USD is available."
        ),
        "completed_utc_dates": [],
    }


_MINOR_CURRENCY_UNITS = {
    # Dukascopy quotes these as cents, so one quote unit is one hundredth
    # of the corresponding major currency.
    "USX": ("USD", 0.01),
    "GBX": ("GBP", 0.01),
}


def _shortest_conversion_route(
    source_currency: str,
    instruments,
) -> list[dict] | None:
    """Find a deterministic shortest route over configured JForex pair symbols."""
    if source_currency == "USD":
        return []
    if not isinstance(instruments, dict):
        instruments = {}
    adjacency: dict[str, list[dict]] = {}
    allowed_groups = {
        "FX_CROSSES", "FX_MAJORS", "FX_RSRV", "VCCY", "FX_METALS"
    }
    for instrument, mapping in sorted(instruments.items()):
        if not isinstance(mapping, dict):
            continue
        if mapping.get("catalog_group") not in allowed_groups:
            continue
        base = str(mapping.get("base_currency", "")).upper()
        quote = str(mapping.get("quote_currency", "")).upper()
        if not re.fullmatch(r"[A-Z]{3}", base) or not re.fullmatch(r"[A-Z]{3}", quote):
            continue
        adjacency.setdefault(base, []).append(
            {
                "from_currency": base,
                "to_currency": quote,
                "instrument": instrument,
                "direction": "direct",
            }
        )
        adjacency.setdefault(quote, []).append(
            {
                "from_currency": quote,
                "to_currency": base,
                "instrument": instrument,
                "direction": "inverse",
            }
        )
    for edges in adjacency.values():
        edges.sort(key=lambda edge: (edge["instrument"], edge["to_currency"]))

    queue = deque([(source_currency, [])])
    visited = {source_currency}
    while queue:
        currency, path = queue.popleft()
        for edge in adjacency.get(currency, []):
            destination = edge["to_currency"]
            next_path = [*path, edge]
            if destination == "USD":
                return next_path
            if destination not in visited:
                visited.add(destination)
                queue.append((destination, next_path))

    return None


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


def resolve_conversion_route_rate(
    quote_currency: str,
    event_time_ms: int,
    route,
    observations_by_instrument,
    *,
    quote_currency_unit_scale: float = 1.0,
) -> float:
    """Multiply event-time rates along a frozen route, then scale minor units."""
    currency = str(quote_currency).strip().upper()
    if isinstance(event_time_ms, bool) or not isinstance(event_time_ms, int):
        raise ValueError("event_time_ms must be an integer UTC epoch-millisecond value.")
    try:
        unit_scale = float(quote_currency_unit_scale)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FXConversionUnavailable(currency, event_time_ms) from exc
    if not math.isfinite(unit_scale) or unit_scale <= 0:
        raise FXConversionUnavailable(currency, event_time_ms)
    rate = unit_scale
    for leg in route or []:
        instrument = str(leg.get("instrument", ""))
        direction = str(leg.get("direction", ""))
        observations = (observations_by_instrument or {}).get(instrument, [])
        pair_currency = str(leg.get("from_currency", currency))
        rate *= resolve_quote_to_usd_rate(
            pair_currency,
            event_time_ms,
            observations,
            direction=direction,
        )
        if not math.isfinite(rate) or rate <= 0:
            raise FXConversionUnavailable(currency, event_time_ms)
    return rate
