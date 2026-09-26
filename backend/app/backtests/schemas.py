"""Persistence and API schema helpers for Backtest resources."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from bson import ObjectId

from app.utils.datetime_utils import utc_now


RUN_STATUSES = frozenset({"preparing", "ready"})
PRICE_MODE = "combined_midpoint"
SOURCE_SIDE = "COMB"
VOLUME_SEMANTICS = "two_sided_quote_liquidity"
DEFAULT_CANDLEKIT_VERSION = "0.1.0"
DRAWING_SCHEMA_VERSION = 1
# A generous v1 limit for a chart drawing export that remains well below
# MongoDB's 16 MiB document limit, leaving room for BSON metadata and indexes.
MAX_DRAWING_STATE_BYTES = 1_048_576


def create_backtest_run_doc(
    *,
    run_id: ObjectId,
    user_id: ObjectId,
    account_id: ObjectId,
    preparation_job_id: ObjectId,
    instrument: str,
    start_date: date,
    end_date: date,
    display_timezone: str,
    start_utc_ms: int,
    end_utc_ms: int,
) -> dict[str, Any]:
    """Build a preparing run document with stable source semantics."""
    now = utc_now()
    return {
        "_id": run_id,
        "user_id": user_id,
        "instrument": instrument,
        "requested_start_date": start_date.isoformat(),
        "requested_end_date": end_date.isoformat(),
        "display_timezone": display_timezone,
        "start_utc_ms": start_utc_ms,
        "end_utc_ms": end_utc_ms,
        "source": "dukascopy",
        "source_interval_minutes": 1,
        "source_side": SOURCE_SIDE,
        "price_mode": PRICE_MODE,
        "volume_semantics": VOLUME_SEMANTICS,
        "status": "preparing",
        "progress": {"stage": "downloading", "percent": None},
        "account_id": account_id,
        "preparation_job_id": preparation_job_id,
        "snapshot": None,
        "coverage": None,
        "replay_cursor": None,
        "created_at": now,
        "updated_at": now,
    }


def create_preparation_job_doc(
    *,
    job_id: ObjectId,
    user_id: ObjectId,
    run_id: ObjectId,
    instrument: str,
    requested_start_date: date,
    requested_end_date: date,
    start_utc_date: date,
    end_utc_date: date,
    staging_prefix: str,
) -> dict[str, Any]:
    """Build the durable queued preparation job for a run."""
    now = utc_now()
    return {
        "_id": job_id,
        "user_id": user_id,
        "run_id": run_id,
        "instrument": instrument,
        "requested_start_date": requested_start_date.isoformat(),
        "requested_end_date": requested_end_date.isoformat(),
        "state": "queued",
        "lease_owner": None,
        "lease_expires_at": None,
        "attempt_count": 0,
        "completed_utc_dates": [],
        "next_utc_date": datetime.combine(
            start_utc_date, time.min, tzinfo=timezone.utc
        ),
        "end_utc_date": datetime.combine(
            end_utc_date, time.min, tzinfo=timezone.utc
        ),
        "staging_prefix": staging_prefix,
        "created_at": now,
        "updated_at": now,
    }


def serialize_backtest_value(value):
    """Recursively convert BSON and date values to JSON-compatible data."""
    if isinstance(value, ObjectId):
        return str(value)
    # MongoDB returns UTC datetimes as naive values by default. Preserve the
    # UTC meaning in API responses rather than exposing a timezone-less time.
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            ("id" if key == "_id" else key): serialize_backtest_value(item)
            for key, item in value.items()
            if key
            not in {
                "user_id",
                "preparation_lease_owner",
                "preparation_lease_expires_at",
                "preparation_lease_generation",
            }
            and (not key.startswith("_") or key == "_id")
        }
    if isinstance(value, list):
        return [serialize_backtest_value(item) for item in value]
    return value


def serialize_run(run: dict, account: dict | None = None) -> dict:
    """Serialize a run and its account label for the public API."""
    result = serialize_backtest_value(run)
    if account is not None:
        result["account_label"] = account.get("display_name") or account.get(
            "account_name"
        )
    return result


def serialize_notice(notice: dict) -> dict:
    """Serialize a user-facing preparation notice."""
    return serialize_backtest_value(notice)


def serialize_drawing_state(document: dict | None, interval_minutes: int) -> dict:
    """Return the stable drawing-state API shape for saved or empty state."""
    if document is None:
        return {
            "interval_minutes": interval_minutes,
            "candlekit_version": DEFAULT_CANDLEKIT_VERSION,
            "schema_version": DRAWING_SCHEMA_VERSION,
            "revision": 0,
            "serialized_state": None,
        }
    return {
        "interval_minutes": document["interval_minutes"],
        "candlekit_version": document["candlekit_version"],
        "schema_version": document["schema_version"],
        "revision": document["revision"],
        "serialized_state": document["serialized_state"],
    }
