"""Stable trade fingerprint helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from typing import Any, Mapping


def _normalize_datetime(value: Any) -> str:
    """Return a stable UTC ISO string for fingerprinting."""
    if isinstance(value, datetime):
        dt_value = value
    else:
        dt_value = datetime.fromisoformat(str(value))

    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=timezone.utc)
    else:
        dt_value = dt_value.astimezone(timezone.utc)

    return dt_value.isoformat()


def _normalize_decimal(value: Any) -> str:
    """Return a stable decimal string for numeric fields."""
    decimal_value = Decimal(str(value))
    normalized = format(decimal_value.normalize(), "f")
    normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def build_trade_fingerprint(trade: Mapping[str, Any]) -> str:
    """Build the stable trade fingerprint required for restore dedupe."""
    fingerprint_parts = [
        str(trade.get("source") or ""),
        str(trade.get("symbol") or ""),
        str(trade.get("side") or ""),
        _normalize_datetime(trade.get("entry_time")),
        _normalize_datetime(trade.get("exit_time")),
        str(int(trade.get("total_quantity") or 0)),
        _normalize_decimal(trade.get("avg_entry_price") or 0),
        _normalize_decimal(trade.get("avg_exit_price") or 0),
    ]
    digest = hashlib.sha256(
        "|".join(fingerprint_parts).encode("utf-8")
    )
    return digest.hexdigest()