"""Symbol helpers for market-data lookup and point values."""

import math
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

# Normalized base symbol -> dollar value per point.
DEFAULT_BASE_SYMBOL_MAP = {
    "MES": {
        "dollar_value_per_point": 5.0,
    },
    "ES": {
        "dollar_value_per_point": 50.0,
    },
    "MNQ": {
        "dollar_value_per_point": 2.0,
    },
    "NQ": {
        "dollar_value_per_point": 20.0,
    },
    "MYM": {
        "dollar_value_per_point": 0.5,
    },
    "YM": {
        "dollar_value_per_point": 5.0,
    },
    "MCL": {
        "dollar_value_per_point": 100.0,
    },
    "CL": {
        "dollar_value_per_point": 1000.0,
    },
    "GC": {
        "dollar_value_per_point": 100.0,
    },
    "MGC": {
        "dollar_value_per_point": 10.0,
    },
}

DEFAULT_FOREX_MAP = {
    "EUR/USD": {
        "base_currency": "EUR",
        "quote_currency": "USD",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000.0,
    },
    "GBP/USD": {
        "base_currency": "GBP",
        "quote_currency": "USD",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000.0,
    },
    "AUD/USD": {
        "base_currency": "AUD",
        "quote_currency": "USD",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000.0,
    },
    "NZD/USD": {
        "base_currency": "NZD",
        "quote_currency": "USD",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000.0,
    },
    "USD/JPY": {
        "base_currency": "USD",
        "quote_currency": "JPY",
        "pip_size": 0.01,
        "price_precision": 3,
        "contract_size": 100000.0,
    },
    "USD/CHF": {
        "base_currency": "USD",
        "quote_currency": "CHF",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000.0,
    },
    "USD/CAD": {
        "base_currency": "USD",
        "quote_currency": "CAD",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000.0,
    },
    "BTC/USD": {
        "base_currency": "BTC",
        "quote_currency": "USD",
        "pip_size": 1.0,
        "price_precision": 2,
        "contract_size": 1.0,
    },
}

DEFAULT_FOREX_CONTRACT_SIZE = 100000.0


def get_default_symbol_mappings() -> dict[str, Any]:
    """Return a copy of the built-in default symbol mappings."""
    mappings: dict[str, Any] = {
        symbol: dict(mapping)
        for symbol, mapping in DEFAULT_BASE_SYMBOL_MAP.items()
    }
    mappings["forex"] = get_default_forex_mappings()
    return mappings


def get_default_forex_mappings() -> dict[str, dict[str, Any]]:
    """Return a copy of the built-in forex instrument mappings."""
    return {
        symbol: dict(mapping)
        for symbol, mapping in DEFAULT_FOREX_MAP.items()
    }


def get_default_market_data_mappings() -> dict[str, str]:
    """Return the default market-data mapping configuration."""
    return {}


def validate_symbol_mappings(
    symbol_mappings: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate and normalize a symbol mapping configuration."""
    if not isinstance(symbol_mappings, Mapping):
        raise ValueError(
            "Symbol mappings must be an object."
        )

    base_symbols = _extract_base_symbol_mappings(
        symbol_mappings
    )

    normalized_base_symbols: dict[str, dict[str, Any]] = {}
    for symbol, mapping in base_symbols.items():
        normalized_symbol = _normalize_mapping_string(
            symbol,
            field_name="base symbol",
        ).upper()
        if not isinstance(mapping, Mapping):
            raise ValueError(
                f"Mapping for {normalized_symbol} must be an object."
            )

        normalized_base_symbols[normalized_symbol] = {
            "dollar_value_per_point": _normalize_mapping_number(
                mapping.get("dollar_value_per_point"),
                field_name=(
                    f"{normalized_symbol} dollar_value_per_point"
                ),
            ),
        }

    normalized_mappings: dict[str, Any] = normalized_base_symbols
    forex_mappings = _extract_forex_mappings(symbol_mappings)
    if forex_mappings is not None:
        normalized_mappings["forex"] = _validate_forex_mappings(
            forex_mappings
        )

    return normalized_mappings


def validate_market_data_mappings(
    market_data_mappings: Mapping[str, Any]
) -> dict[str, str]:
    """Validate and normalize market-data prefix mappings."""
    if not isinstance(market_data_mappings, Mapping):
        raise ValueError(
            "Market data mappings must be an object."
        )

    normalized_mappings: dict[str, str] = {}
    for source_symbol, target_symbol in market_data_mappings.items():
        normalized_source = _normalize_symbol_candidate(
            _normalize_mapping_string(
                source_symbol,
                field_name="market data mapping source",
            )
        )
        normalized_target = _normalize_symbol_candidate(
            _normalize_mapping_string(
                target_symbol,
                field_name=(
                    f"{normalized_source} market data mapping target"
                ),
            )
        )
        normalized_mappings[normalized_source] = normalized_target

    return normalized_mappings


def get_effective_symbol_mappings(
    symbol_mappings: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return validated user mappings or the built-in defaults."""
    effective_mappings = get_default_symbol_mappings()
    if symbol_mappings is None:
        return effective_mappings

    try:
        normalized_mappings = validate_symbol_mappings(
            symbol_mappings
        )
        forex_mappings = normalized_mappings.pop("forex", None)
        effective_mappings.update(normalized_mappings)
        if forex_mappings is not None:
            # An explicitly supplied forex section is authoritative so the
            # settings UI can remove a built-in pair. Missing forex settings
            # continue to hydrate from defaults for legacy users.
            effective_mappings["forex"] = forex_mappings
        return effective_mappings
    except ValueError:
        return effective_mappings


def get_effective_forex_mappings(
    symbol_mappings: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Return validated forex mappings, hydrating only missing settings."""
    effective_mappings = get_default_forex_mappings()
    if symbol_mappings is None:
        return effective_mappings

    try:
        normalized_mappings = validate_symbol_mappings(
            symbol_mappings
        )
        if "forex" in normalized_mappings:
            effective_mappings = normalized_mappings["forex"]
    except ValueError:
        return effective_mappings

    return effective_mappings


def get_forex_instrument(
    symbol: str,
    raw_symbol: str | None = None,
    symbol_mappings: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the configured forex instrument for an exact pair."""
    forex_mappings = get_effective_forex_mappings(
        symbol_mappings
    )
    for candidate in _iter_symbol_candidates(symbol, raw_symbol):
        if candidate in forex_mappings:
            return dict(forex_mappings[candidate])
    return None


def is_forex_symbol(
    symbol: str,
    raw_symbol: str | None = None,
    symbol_mappings: Mapping[str, Any] | None = None,
) -> bool:
    """Return whether a symbol is an exact configured forex pair."""
    return get_forex_instrument(
        symbol,
        raw_symbol,
        symbol_mappings,
    ) is not None


def get_forex_usd_multiplier(
    instrument: Mapping[str, Any],
    quote_to_usd_rate: Any = None,
) -> float:
    """Return USD P&L per one price unit and one standard lot."""
    quote_currency = str(
        instrument.get("quote_currency", "")
    ).upper()
    if quote_currency and quote_currency != "USD" and quote_to_usd_rate is None:
        raise ValueError(
            "A quote-to-USD rate is required for non-USD forex trades."
        )
    try:
        contract_size = Decimal(
            str(instrument["contract_size"])
        )
        rate = Decimal(
            "1"
            if quote_to_usd_rate is None
            else str(quote_to_usd_rate)
        )
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            "Forex contract size and quote conversion rate must be numeric."
        ) from exc

    if (
        not contract_size.is_finite()
        or not rate.is_finite()
        or contract_size <= 0
        or rate <= 0
    ):
        raise ValueError(
            "Forex contract size and quote conversion rate must be greater than zero."
        )
    return float(contract_size * rate)


def get_trade_usd_multiplier(
    trade: Mapping[str, Any],
    symbol_mappings: Mapping[str, Any] | None = None,
) -> float:
    """Resolve the USD P&L multiplier for a stored trade."""
    if str(trade.get("instrument_type", "")).lower() == "forex":
        return get_forex_usd_multiplier(
            {
                "contract_size": trade.get("contract_size"),
                "quote_currency": trade.get(
                    "quote_currency"
                ),
            },
            trade.get("quote_to_usd_rate"),
        )

    return get_point_value(
        str(trade.get("symbol", "")),
        trade.get("raw_symbol"),
        symbol_mappings,
    )


def get_effective_market_data_mappings(
    market_data_mappings: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Return validated user market-data mappings or an empty mapping."""
    if market_data_mappings is None:
        return get_default_market_data_mappings()

    try:
        return validate_market_data_mappings(
            market_data_mappings
        )
    except ValueError:
        return get_default_market_data_mappings()


def get_point_value(
    symbol: str,
    raw_symbol: str | None = None,
    symbol_mappings: Mapping[str, Any] | None = None,
) -> float:
    """Resolve dollar value per point for a symbol."""
    mapping_entry = _find_mapping_entry(
        symbol,
        raw_symbol,
        symbol_mappings,
    )
    if mapping_entry is None:
        normalized_symbol = _normalize_symbol_candidate(
            raw_symbol or symbol
        )
        raise ValueError(
            "No dollar value per point is configured for "
            f"symbol '{normalized_symbol}'."
        )
    return float(mapping_entry["dollar_value_per_point"])


def resolve_market_data_symbol(
    symbol: str,
    raw_symbol: str | None = None,
    market_data_mappings: Mapping[str, Any] | None = None,
) -> str:
    """Resolve the canonical symbol key used for stored market data."""

    effective_mappings = get_effective_market_data_mappings(
        market_data_mappings
    )
    base_symbol = _resolve_base_symbol(symbol, raw_symbol)
    return _resolve_market_data_mapping(
        base_symbol,
        effective_mappings,
    )


def resolve_market_data_storage_symbol(
    symbol: str,
    raw_symbol: str | None = None,
    market_data_mappings: Mapping[str, Any] | None = None,
) -> str:
    """Return the canonical symbol key used for dataset storage."""

    return resolve_market_data_symbol(
        symbol,
        raw_symbol,
        market_data_mappings,
    )


def resolve_market_data_symbols(
    symbol: str,
    raw_symbol: str | None = None,
    market_data_mappings: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return preferred and fallback market-data keys in priority order."""

    resolved_symbols: list[str] = []
    seen: set[str] = set()
    effective_mappings = get_effective_market_data_mappings(
        market_data_mappings
    )
    storage_symbol = resolve_market_data_storage_symbol(
        symbol,
        raw_symbol,
        effective_mappings,
    )
    if storage_symbol:
        resolved_symbols.append(storage_symbol)
        seen.add(storage_symbol)

    for candidate in _iter_symbol_candidates(symbol, raw_symbol):
        for resolved_candidate in (
            _resolve_market_data_mapping(
                candidate,
                effective_mappings,
            ),
            candidate,
        ):
            if not resolved_candidate or resolved_candidate in seen:
                continue
            resolved_symbols.append(resolved_candidate)
            seen.add(resolved_candidate)

    if resolved_symbols:
        return resolved_symbols

    fallback = _resolve_market_data_mapping(
        _normalize_symbol_candidate(symbol),
        effective_mappings,
    )
    return [fallback] if fallback else []


def _find_mapping_entry(
    symbol: str,
    raw_symbol: str | None,
    symbol_mappings: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve the best matching mapping entry for a symbol."""
    mappings = get_effective_symbol_mappings(
        symbol_mappings
    )
    ordered_symbols = sorted(
        mappings,
        key=lambda value: (-len(value), value),
    )

    for candidate in _iter_symbol_candidates(
        symbol,
        raw_symbol,
    ):
        for base_symbol in ordered_symbols:
            mapping = mappings.get(base_symbol)
            if not isinstance(mapping, Mapping):
                continue
            if "dollar_value_per_point" not in mapping:
                continue
            if candidate.startswith(base_symbol):
                return dict(mapping)

    return None


def _extract_base_symbol_mappings(
    symbol_mappings: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Return flat base-symbol mappings from new or legacy shapes."""
    if "base_symbols" in symbol_mappings:
        base_symbols = symbol_mappings.get("base_symbols")
        if not isinstance(base_symbols, Mapping):
            raise ValueError(
                "base_symbols must be an object."
            )
        return base_symbols

    if "futures" in symbol_mappings:
        futures = symbol_mappings.get("futures")
        if not isinstance(futures, Mapping):
            raise ValueError("futures must be an object.")
        return futures

    return {
        symbol: mapping
        for symbol, mapping in symbol_mappings.items()
        if str(symbol).lower() != "forex"
    }


def _extract_forex_mappings(
    symbol_mappings: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Return the nested forex section when present."""
    if "forex" not in symbol_mappings:
        return None
    forex_mappings = symbol_mappings.get("forex")
    if not isinstance(forex_mappings, Mapping):
        raise ValueError("forex must be an object.")
    return forex_mappings


def _validate_forex_mappings(
    forex_mappings: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate and normalize nested forex instrument mappings."""
    normalized: dict[str, dict[str, Any]] = {}
    for pair, mapping in forex_mappings.items():
        normalized_pair = _normalize_mapping_string(
            pair,
            field_name="forex pair",
        ).upper()
        pair_parts = normalized_pair.split("/")
        if len(pair_parts) != 2 or any(
            len(part) != 3
            or not part.isascii()
            or not part.isalpha()
            for part in pair_parts
        ):
            raise ValueError(
                f"Forex pair '{normalized_pair}' must use AAA/BBB format."
            )
        if not isinstance(mapping, Mapping):
            raise ValueError(
                f"Mapping for {normalized_pair} must be an object."
            )

        base_currency = _normalize_currency(
            mapping.get("base_currency"),
            field_name=f"{normalized_pair} base_currency",
        )
        quote_currency = _normalize_currency(
            mapping.get("quote_currency"),
            field_name=f"{normalized_pair} quote_currency",
        )
        if base_currency != pair_parts[0]:
            raise ValueError(
                f"{normalized_pair} base_currency must match the pair."
            )
        if quote_currency != pair_parts[1]:
            raise ValueError(
                f"{normalized_pair} quote_currency must match the pair."
            )

        pip_size = _normalize_mapping_number(
            mapping.get("pip_size"),
            field_name=f"{normalized_pair} pip_size",
        )
        price_precision = _normalize_mapping_integer(
            mapping.get("price_precision"),
            field_name=f"{normalized_pair} price_precision",
            minimum=0,
        )
        contract_size = _normalize_mapping_number(
            mapping.get(
                "contract_size",
                DEFAULT_FOREX_CONTRACT_SIZE,
            ),
            field_name=f"{normalized_pair} contract_size",
        )
        normalized[normalized_pair] = {
            "base_currency": base_currency,
            "quote_currency": quote_currency,
            "pip_size": pip_size,
            "price_precision": price_precision,
            "contract_size": contract_size,
        }

    return normalized


def _normalize_currency(value: Any, field_name: str) -> str:
    """Normalize a three-letter currency code."""
    currency = _normalize_mapping_string(
        value,
        field_name=field_name,
    ).upper()
    if (
        len(currency) != 3
        or not currency.isascii()
        or not currency.isalpha()
    ):
        raise ValueError(
            f"{field_name} must be a three-letter currency code."
        )
    return currency


def _normalize_mapping_integer(
    value: Any,
    field_name: str,
    minimum: int = 1,
) -> int:
    """Normalize a non-negative integer mapping field."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer.")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be an integer."
        ) from exc
    if not decimal_value.is_finite() or decimal_value != decimal_value.to_integral_value():
        raise ValueError(f"{field_name} must be an integer.")
    normalized = int(decimal_value)
    if normalized < minimum:
        raise ValueError(
            f"{field_name} must be at least {minimum}."
        )
    return normalized


def _iter_symbol_candidates(
    symbol: str,
    raw_symbol: str | None,
) -> list[str]:
    """Return candidate symbol strings for prefix matching."""
    candidates: list[str] = []
    seen: set[str] = set()

    for candidate in (symbol, raw_symbol):
        if candidate is None:
            continue

        normalized = _normalize_symbol_candidate(candidate)
        if normalized and normalized not in seen:
            candidates.append(normalized)
            seen.add(normalized)

    return candidates


def _resolve_base_symbol(
    symbol: str,
    raw_symbol: str | None,
) -> str:
    """Resolve the normalized instrument/base symbol for storage."""

    mappings = _extract_base_symbol_mappings(
        get_default_symbol_mappings()
    )
    ordered_symbols = sorted(
        mappings,
        key=lambda value: (-len(value), value),
    )

    for candidate in _iter_symbol_candidates(symbol, raw_symbol):
        for base_symbol in ordered_symbols:
            if candidate.startswith(base_symbol):
                return base_symbol

    for candidate in _iter_symbol_candidates(symbol, raw_symbol):
        head = candidate.split(" ", 1)[0]
        if head:
            return head

    return _normalize_symbol_candidate(symbol)


def _normalize_symbol_candidate(value: str) -> str:
    """Normalize a symbol string for prefix matching."""
    return " ".join(value.strip().upper().split())


def _resolve_market_data_mapping(
    value: str,
    market_data_mappings: Mapping[str, str],
) -> str:
    """Apply the best matching market-data mapping to a symbol."""
    normalized = _normalize_symbol_candidate(value)
    if not normalized:
        return normalized

    for source_symbol in sorted(
        market_data_mappings,
        key=len,
        reverse=True,
    ):
        if not normalized.startswith(source_symbol):
            continue

        suffix = normalized[len(source_symbol):]
        if suffix and not suffix.startswith(" "):
            return (
                f"{market_data_mappings[source_symbol]}"
                f"{suffix}"
            )
        return (
            f"{market_data_mappings[source_symbol]}"
            f"{suffix}"
        )

    return normalized


def _normalize_mapping_string(
    value: Any, field_name: str
) -> str:
    """Normalize a symbol mapping string field."""
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a string."
        )

    normalized = value.strip()
    if not normalized:
        raise ValueError(
            f"{field_name} must not be empty."
        )

    return normalized


def _normalize_mapping_number(
    value: Any,
    field_name: str,
) -> float:
    """Normalize a numeric symbol mapping field."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number.")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a number."
        ) from exc

    if not decimal_value.is_finite():
        raise ValueError(
            f"{field_name} must be a finite number."
        )
    normalized = float(decimal_value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )

    return normalized
