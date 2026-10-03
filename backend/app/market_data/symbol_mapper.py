"""Symbol helpers for market-data lookup and point values."""

import json
import math
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
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
_DEFAULT_INSTRUMENT_SPEC_PATH = (
    Path(__file__).with_name("data") / "dukascopy_instrument_specs_v1.json"
)
_DEFAULT_INSTRUMENT_MAPPING_FIELDS = (
    "base_currency",
    "quote_currency",
    "quote_currency_unit_scale",
    "pip_size",
    "tick_size",
    "contract_size",
    "min_lots",
    "lot_increment",
    "supported_for_simulation",
    "reason",
    "spec_source",
    "catalog_group",
)


def price_precision_from_tick_size(value: Any) -> int:
    """Return the decimal places needed to represent a positive price tick."""
    try:
        tick_size = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("tick_size must be a positive finite number.") from exc
    if not tick_size.is_finite() or tick_size <= 0:
        raise ValueError("tick_size must be a positive finite number.")
    precision = max(0, -tick_size.normalize().as_tuple().exponent)
    if precision > 15:
        raise ValueError("tick_size implies price precision greater than 15 places.")
    return precision


@lru_cache(maxsize=1)
def _load_default_instrument_specs() -> dict[str, dict[str, Any]]:
    """Load the checked-in, versioned catalog and sizing snapshot."""
    with _DEFAULT_INSTRUMENT_SPEC_PATH.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    version = payload.get("spec_version")
    rows = payload.get("instruments")
    if not isinstance(version, str) or not isinstance(rows, list):
        raise RuntimeError("The Dukascopy instrument specification file is invalid.")
    specs: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("instrument"), str):
            raise RuntimeError("The Dukascopy instrument specification file is invalid.")
        code = row["instrument"].upper()
        specs[code] = {
            key: row.get(key)
            for key in _DEFAULT_INSTRUMENT_MAPPING_FIELDS
        }
        try:
            specs[code]["price_precision"] = (
                price_precision_from_tick_size(specs[code]["tick_size"])
                if specs[code]["tick_size"] is not None
                else None
            )
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid tick size for Dukascopy instrument {code}."
            ) from exc
        specs[code]["spec_version"] = version
    return specs


def get_default_instrument_mappings() -> dict[str, dict[str, Any]]:
    """Return a copy of the versioned JForex settings table defaults."""
    return {
        instrument: dict(mapping)
        for instrument, mapping in _load_default_instrument_specs().items()
    }


def get_default_instrument_specs_version() -> str:
    """Return the version tag for the checked-in JForex catalog snapshot."""
    specs = _load_default_instrument_specs()
    first = next(iter(specs.values()), {})
    return str(first.get("spec_version", "unknown"))


def get_default_symbol_mappings() -> dict[str, Any]:
    """Return a copy of the built-in default symbol mappings."""
    mappings: dict[str, Any] = {
        symbol: dict(mapping)
        for symbol, mapping in DEFAULT_BASE_SYMBOL_MAP.items()
    }
    mappings["forex"] = get_default_forex_mappings()
    mappings["instruments"] = get_default_instrument_mappings()
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
    instrument_mappings = _extract_instrument_mappings(symbol_mappings)
    if instrument_mappings is not None:
        normalized_mappings["instruments"] = _validate_instrument_mappings(
            instrument_mappings
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
        instrument_mappings = normalized_mappings.pop("instruments", None)
        effective_mappings.update(normalized_mappings)
        if forex_mappings is not None:
            # An explicitly supplied forex section is authoritative so the
            # settings UI can remove a built-in pair. Missing forex settings
            # continue to hydrate from defaults for legacy users.
            effective_mappings["forex"] = forex_mappings
        if instrument_mappings is not None:
            effective_instruments = dict(effective_mappings.get("instruments", {}))
            for instrument, mapping in instrument_mappings.items():
                effective_instruments[instrument] = {
                    **effective_instruments.get(instrument, {}),
                    **mapping,
                }
            effective_mappings["instruments"] = effective_instruments
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


def get_simulation_instrument(
    symbol: str,
    raw_symbol: str | None = None,
    symbol_mappings: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str] | None:
    """Resolve a configured contract mapping for backtest execution.

    Exact instrument mappings are preferred. Existing Forex settings remain a
    compatible fallback for runs and profiles that predate the generic table.
    The returned type is ``forex`` for canonical three-letter pairs and
    ``contract`` for other configured instruments.
    """
    try:
        normalized = validate_symbol_mappings(symbol_mappings or {})
    except ValueError:
        normalized = {}
    candidates = _iter_instrument_candidates(symbol, raw_symbol)
    defaults = _load_default_instrument_specs()
    instruments = normalized.get("instruments", {})
    forex_mappings = normalized.get("forex", {})

    for candidate in candidates:
        default = defaults.get(candidate)
        explicit = instruments.get(candidate) if isinstance(instruments, Mapping) else None
        if isinstance(explicit, Mapping):
            mapping = {**(default or {}), **explicit}
            return mapping, _simulation_mapping_type(mapping)

    # A legacy Forex row remains authoritative until the unified instrument
    # table has an explicit row for the same exact symbol.
    if isinstance(symbol_mappings, Mapping) and isinstance(forex_mappings, Mapping):
        raw_forex = symbol_mappings.get("forex")
        if isinstance(raw_forex, Mapping):
            for candidate in candidates:
                pair_alias = candidate.replace("-", "/")
                legacy = forex_mappings.get(pair_alias)
                if isinstance(legacy, Mapping) and pair_alias in raw_forex:
                    default = defaults.get(candidate)
                    merged = {**(default or {}), **legacy}
                    if legacy.get("price_precision") is not None:
                        # Older profiles saved decimal precision instead of a
                        # tick size. Preserve that saved grid when defaults
                        # provide a tick for the same pair.
                        merged["tick_size"] = float(
                            Decimal(1).scaleb(-int(legacy["price_precision"]))
                        )
                    return merged, "forex"

    for candidate in candidates:
        mapping = defaults.get(candidate)
        if isinstance(mapping, Mapping):
            return dict(mapping), _simulation_mapping_type(mapping)

    forex = get_forex_instrument(
        symbol,
        raw_symbol=raw_symbol,
        symbol_mappings=symbol_mappings,
    )
    if forex is not None:
        return forex, "forex"
    return None


def _simulation_mapping_type(mapping: Mapping[str, Any]) -> str:
    """Classify source FX pairs while keeping other instruments as CFDs."""
    return "forex" if mapping.get("catalog_group") in {
        "FX_CROSSES", "FX_MAJORS", "FX_RSRV"
    } else "contract"


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
    if (
        str(trade.get("instrument_type", "")).lower()
        in {"forex", "contract", "cfd"}
        and trade.get("contract_size") is not None
    ):
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
        if str(symbol).lower() not in {"forex", "instruments"}
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


def _extract_instrument_mappings(
    symbol_mappings: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Return the generic simulated-trading instrument section."""
    if "instruments" not in symbol_mappings:
        return None
    mappings = symbol_mappings.get("instruments")
    if not isinstance(mappings, Mapping):
        raise ValueError("instruments must be an object.")
    return mappings


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


def _validate_instrument_mappings(
    instrument_mappings: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate settings-driven pricing and lot contracts for any instrument."""
    normalized: dict[str, dict[str, Any]] = {}
    seen_aliases: set[str] = set()
    for instrument, mapping in instrument_mappings.items():
        code = _normalize_mapping_string(
            instrument,
            field_name="instrument code",
        ).upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]{0,63}", code):
            raise ValueError(
                f"Instrument code '{code}' contains unsupported characters."
            )
        alias = code.replace("/", "-")
        if alias in seen_aliases:
            raise ValueError(f"Duplicate instrument mapping for {alias}.")
        seen_aliases.add(alias)
        if not isinstance(mapping, Mapping):
            raise ValueError(f"Mapping for {code} must be an object.")
        base_currency = _normalize_unit_label(
            mapping.get("base_currency"),
            field_name=f"{code} base_currency",
        )
        quote_currency = _normalize_currency(
            mapping.get("quote_currency"),
            field_name=f"{code} quote_currency",
        )
        tick_size = _optional_positive_mapping_number(
            mapping.get("tick_size"),
            field_name=f"{code} tick_size",
        )
        price_precision = (
            price_precision_from_tick_size(tick_size)
            if tick_size is not None
            else _optional_mapping_integer(
                mapping.get("price_precision"),
                field_name=f"{code} price_precision",
                minimum=0,
            )
        )
        if price_precision is not None and price_precision > 15:
            raise ValueError(f"{code} price_precision cannot exceed 15.")
        normalized_mapping: dict[str, Any] = {
            "base_currency": base_currency,
            "quote_currency": quote_currency,
            "quote_currency_unit_scale": _optional_positive_mapping_number(
                mapping.get("quote_currency_unit_scale", 1),
                field_name=f"{code} quote_currency_unit_scale",
                default=1,
            ),
            "pip_size": _optional_positive_mapping_number(
                mapping.get("pip_size"),
                field_name=f"{code} pip_size",
            ),
            "tick_size": tick_size,
            "price_precision": price_precision,
            "contract_size": _optional_positive_mapping_number(
                mapping.get("contract_size"),
                field_name=f"{code} contract_size",
            ),
            "min_lots": _optional_positive_mapping_number(
                mapping.get("min_lots"),
                field_name=f"{code} min_lots",
            ),
            "lot_increment": _optional_positive_mapping_number(
                mapping.get("lot_increment"),
                field_name=f"{code} lot_increment",
            ),
        }
        complete = all(
            normalized_mapping[field] is not None
            for field in (
                "pip_size", "tick_size", "price_precision", "contract_size",
                "min_lots", "lot_increment",
            )
        )
        enabled = mapping.get("supported_for_simulation", complete)
        if not isinstance(enabled, bool):
            raise ValueError(f"{code} supported_for_simulation must be a boolean.")
        normalized_mapping["supported_for_simulation"] = enabled and complete
        reason = mapping.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError(f"{code} reason must be a string when provided.")
        normalized_mapping["reason"] = (
            reason
            if normalized_mapping["supported_for_simulation"]
            else reason or "Complete verified pricing and lot-size settings are required."
        )
        spec_source = mapping.get("spec_source")
        if spec_source is not None and not isinstance(spec_source, str):
            raise ValueError(f"{code} spec_source must be a string when provided.")
        normalized_mapping["spec_source"] = spec_source
        catalog_group = mapping.get("catalog_group")
        normalized_mapping["catalog_group"] = (
            catalog_group if isinstance(catalog_group, str) else None
        )
        normalized[code] = normalized_mapping
    return normalized


def _normalize_unit_label(value: Any, field_name: str) -> str:
    """Normalize a base asset or unit label, such as EUR, shares, or ounces."""
    label = _normalize_mapping_string(value, field_name=field_name).upper()
    if len(label) > 24 or not re.fullmatch(r"[A-Z0-9][A-Z0-9.+_ -]{0,23}", label):
        raise ValueError(f"{field_name} must be a short asset or unit label.")
    return label


def _iter_instrument_candidates(
    symbol: str,
    raw_symbol: str | None,
) -> list[str]:
    """Return exact normalized codes and their slash/dash catalog aliases."""
    candidates: list[str] = []
    seen: set[str] = set()
    for source in (symbol, raw_symbol):
        if not isinstance(source, str):
            continue
        normalized = _normalize_symbol_candidate(source)
        for candidate in (normalized, normalized.replace("/", "-"), normalized.replace("-", "/")):
            if candidate and candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)
    return candidates


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


def _optional_mapping_integer(
    value: Any,
    *,
    field_name: str,
    minimum: int = 1,
) -> int | None:
    """Normalize an optional integer used by explicitly incomplete catalog rows."""
    if value is None or value == "":
        return None
    return _normalize_mapping_integer(value, field_name, minimum=minimum)


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


def _optional_positive_mapping_number(
    value: Any,
    *,
    field_name: str,
    default: float | None = None,
) -> float | None:
    """Normalize an optional positive value, preserving missing specs as None."""
    if value is None or value == "":
        return default
    return _normalize_mapping_number(value, field_name)
