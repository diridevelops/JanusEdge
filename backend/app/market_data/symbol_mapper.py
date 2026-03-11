"""Symbol mapper helpers for ticker resolution and point values."""

from typing import Any, Mapping

# Normalized base symbol -> Yahoo ticker and dollar value per point.
DEFAULT_BASE_SYMBOL_MAP = {
    "MES": {
        "yahoo_symbol": "MES=F",
        "dollar_value_per_point": 5.0,
    },
    "ES": {
        "yahoo_symbol": "ES=F",
        "dollar_value_per_point": 50.0,
    },
    "MNQ": {
        "yahoo_symbol": "MNQ=F",
        "dollar_value_per_point": 2.0,
    },
    "NQ": {
        "yahoo_symbol": "NQ=F",
        "dollar_value_per_point": 20.0,
    },
    "MYM": {
        "yahoo_symbol": "MYM=F",
        "dollar_value_per_point": 0.5,
    },
    "YM": {
        "yahoo_symbol": "YM=F",
        "dollar_value_per_point": 5.0,
    },
    "MCL": {
        "yahoo_symbol": "MCL=F",
        "dollar_value_per_point": 100.0,
    },
    "CL": {
        "yahoo_symbol": "CL=F",
        "dollar_value_per_point": 1000.0,
    },
    "GC": {
        "yahoo_symbol": "GC=F",
        "dollar_value_per_point": 100.0,
    },
    "MGC": {
        "yahoo_symbol": "MGC=F",
        "dollar_value_per_point": 10.0,
    },
}


def get_default_symbol_mappings() -> dict[str, dict[str, Any]]:
    """Return a copy of the built-in default symbol mappings."""
    return {
        symbol: dict(mapping)
        for symbol, mapping in DEFAULT_BASE_SYMBOL_MAP.items()
    }


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
            "yahoo_symbol": _normalize_mapping_string(
                mapping.get("yahoo_symbol"),
                field_name=(
                    f"{normalized_symbol} yahoo_symbol"
                ),
            ),
            "dollar_value_per_point": _normalize_mapping_number(
                mapping.get("dollar_value_per_point"),
                field_name=(
                    f"{normalized_symbol} dollar_value_per_point"
                ),
            ),
        }

    return normalized_base_symbols


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


def map_to_yahoo(
    symbol: str,
    raw_symbol: str | None = None,
    symbol_mappings: Mapping[str, Any] | None = None,
) -> str:
    """
    Map a platform symbol to a yfinance ticker.

    Parameters:
        symbol: Normalized symbol (e.g. 'MES').
        raw_symbol: Original platform symbol.
        symbol_mappings: User-configurable mapping settings.

    Returns:
        yfinance ticker string (e.g. 'MES=F').

    """
    mapping_entry = _find_mapping_entry(
        symbol,
        raw_symbol,
        symbol_mappings,
    )
    if mapping_entry is not None:
        return str(mapping_entry["yahoo_symbol"])

    clean = _normalize_symbol_candidate(symbol)
    return f"{clean}=F"


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
    return value.strip().upper()


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
