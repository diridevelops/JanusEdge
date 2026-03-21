"""Symbol helpers for market-data lookup and point values."""

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


def get_default_symbol_mappings() -> dict[str, dict[str, Any]]:
    """Return a copy of the built-in default symbol mappings."""
    return {
        symbol: dict(mapping)
        for symbol, mapping in DEFAULT_BASE_SYMBOL_MAP.items()
    }


def get_default_market_data_mappings() -> dict[str, str]:
    """Return the default market-data mapping configuration."""
    return {}


def validate_symbol_mappings(
    symbol_mappings: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
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

    return normalized_base_symbols


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
) -> dict[str, dict[str, Any]]:
    """Return validated user mappings or the built-in defaults."""
    effective_mappings = get_default_symbol_mappings()
    if symbol_mappings is None:
        return effective_mappings

    try:
        effective_mappings.update(
            validate_symbol_mappings(symbol_mappings)
        )
        return effective_mappings
    except ValueError:
        return effective_mappings


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
    """Resolve the symbol key used for stored market data."""

    effective_mappings = get_effective_market_data_mappings(
        market_data_mappings
    )

    for candidate in _iter_symbol_candidates(
        symbol,
        raw_symbol,
    ):
        return _resolve_market_data_mapping(
            candidate,
            effective_mappings,
        )

    return _resolve_market_data_mapping(
        _normalize_symbol_candidate(symbol),
        effective_mappings,
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
            if candidate.startswith(base_symbol):
                return dict(mappings[base_symbol])

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

    return symbol_mappings


def _iter_symbol_candidates(
    symbol: str,
    raw_symbol: str | None,
) -> list[str]:
    """Return candidate symbol strings for prefix matching."""
    candidates: list[str] = []
    seen: set[str] = set()

    for candidate in (raw_symbol, symbol):
        if candidate is None:
            continue

        normalized = _normalize_symbol_candidate(candidate)
        if normalized and normalized not in seen:
            candidates.append(normalized)
            seen.add(normalized)

    return candidates


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
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a number."
        ) from exc

    if normalized <= 0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )

    return normalized
