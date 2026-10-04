"""User-scoped, versioned HistData candle imports for Backtest replay."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
from typing import Iterable

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.backtests.snapshot_store import SnapshotStore
from app.extensions import mongo
from app.utils.errors import ConflictError, NotFoundError, ValidationError


MANUAL_CANDLE_CACHE_VERSION = "manual-histdata-bid-m1-v1"
HISTDATA_TIMEZONE = timezone(timedelta(hours=-5), name="HistData EST")
_CANDLE_FIELDS = ("time_ms", "open", "high", "low", "close", "volume")


def canonical_candle_checksum(candles: list[dict]) -> str:
    """Hash candle values independently of the Parquet writer implementation."""
    normalized = [
        {
            "time_ms": int(row["time_ms"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for row in sorted(candles, key=lambda item: int(item["time_ms"]))
    ]
    for row in normalized:
        for field in _CANDLE_FIELDS[1:]:
            if row[field] == 0:
                row[field] = 0.0
    payload = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _as_user_oid(user_id) -> ObjectId:
    try:
        return user_id if isinstance(user_id, ObjectId) else ObjectId(str(user_id))
    except Exception as exc:
        raise ValidationError("Authenticated user id is invalid.") from exc


def source_date_for_time(time_ms: int) -> date:
    return datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc).astimezone(
        HISTDATA_TIMEZONE
    ).date()


def parse_histdata_files(files: Iterable) -> tuple[dict[date, list[dict]], list[str]]:
    """Parse headerless HistData M1 CSVs and deduplicate identical timestamps."""
    rows: dict[int, tuple[dict, str, int]] = {}
    incoming_dates: set[str] = set()
    saw_file = False
    for file_storage in files:
        if file_storage is None:
            continue
        saw_file = True
        name = (getattr(file_storage, "filename", None) or "upload.csv").strip()
        stream = getattr(file_storage, "stream", file_storage)
        wrapper = None
        if hasattr(stream, "seek"):
            stream.seek(0)
        try:
            wrapper = io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")
            for line_number, raw_line in enumerate(wrapper, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                fields = next(csv.reader([line], delimiter=";"))
                if len(fields) != 6:
                    raise ValidationError(
                        f"{name}, line {line_number}: expected six semicolon-separated fields."
                    )
                stamp_text = fields[0].strip()
                try:
                    local_time = datetime.strptime(
                        stamp_text, "%Y%m%d %H%M%S"
                    ).replace(tzinfo=HISTDATA_TIMEZONE)
                except ValueError as exc:
                    raise ValidationError(
                        f"{name}, line {line_number}: timestamp must use YYYYMMDD HHMMSS."
                    ) from exc
                if local_time.second != 0:
                    raise ValidationError(
                        f"{name}, line {line_number}: HistData M1 timestamps must be minute-aligned."
                    )
                time_ms = int(local_time.astimezone(timezone.utc).timestamp() * 1000)
                try:
                    values = [float(value.strip()) for value in fields[1:]]
                except (ValueError, OverflowError) as exc:
                    raise ValidationError(
                        f"{name}, line {line_number}: OHLCV values must be numeric."
                    ) from exc
                if not all(math.isfinite(value) for value in values):
                    raise ValidationError(
                        f"{name}, line {line_number}: OHLCV values must be finite."
                    )
                open_price, high, low, close, volume = values
                if (
                    high < max(open_price, low, close)
                    or low > min(open_price, high, close)
                    or volume < 0
                ):
                    raise ValidationError(
                        f"{name}, line {line_number}: invalid OHLCV values."
                    )
                candle = {
                    "time_ms": time_ms,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
                previous = rows.get(time_ms)
                if previous is not None and previous[0] != candle:
                    raise ValidationError(
                        f"{name}, line {line_number}: conflicting duplicate timestamp "
                        f"{stamp_text}; remove the conflict before importing."
                    )
                rows[time_ms] = (candle, name, line_number)
                incoming_dates.add(source_date_for_time(time_ms).isoformat())
        except UnicodeDecodeError as exc:
            raise ValidationError(f"{name}: CSV must be UTF-8 text.") from exc
        finally:
            # TextIOWrapper owns the uploaded stream; detach so Flask can clean it up.
            try:
                wrapper.detach()
            except (AttributeError, ValueError):
                pass
    if not saw_file or not rows:
        raise ValidationError("Choose at least one non-empty HistData CSV file.")
    grouped: dict[date, list[dict]] = {}
    for time_ms, (candle, _name, _line) in sorted(rows.items()):
        day = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc).date()
        grouped.setdefault(day, []).append(candle)
    return grouped, sorted(incoming_dates)


class ManualCandleDatasetStore:
    """Persist immutable revision manifests over shared manual candle objects."""

    def __init__(self, snapshot_store: SnapshotStore | None = None):
        self.snapshot_store = snapshot_store or SnapshotStore()

    @property
    def heads(self):
        return mongo.db.backtest_manual_dataset_heads

    @property
    def revisions(self):
        return mongo.db.backtest_manual_dataset_revisions

    def get_active(self, user_id, instrument: str) -> dict | None:
        user_oid = _as_user_oid(user_id)
        normalized = instrument.strip().upper()
        head = self.heads.find_one({"user_id": user_oid, "instrument": normalized})
        if head is None:
            return None
        revision = self.revisions.find_one(
            {"_id": head.get("revision_id"), "user_id": user_oid, "instrument": normalized}
        )
        return revision

    def get_revision(self, user_id, instrument: str, revision_id) -> dict:
        user_oid = _as_user_oid(user_id)
        try:
            revision_oid = ObjectId(str(revision_id))
        except Exception as exc:
            raise NotFoundError("Manual candle dataset revision not found.") from exc
        revision = self.revisions.find_one(
            {
                "_id": revision_oid,
                "user_id": user_oid,
                "instrument": instrument.strip().upper(),
            }
        )
        if revision is None:
            raise NotFoundError("Manual candle dataset revision not found.")
        return revision

    def describe(self, user_id, instrument: str) -> dict:
        revision = self.get_active(user_id, instrument)
        if revision is None:
            return {
                "instrument": instrument.strip().upper(),
                "revision": None,
                "available_dates": [],
                "candle_count": 0,
            }
        return {
            "instrument": revision["instrument"],
            "revision": str(revision["_id"]),
            "available_dates": list(revision.get("source_dates", [])),
            "candle_count": int(revision.get("candle_count", 0)),
            "first_date": min(revision.get("source_dates", []), default=None),
            "last_date": max(revision.get("source_dates", []), default=None),
        }

    def preview(self, user_id, instrument: str, files: Iterable) -> dict:
        normalized = instrument.strip().upper()
        grouped, incoming_source_dates = parse_histdata_files(files)
        revision = self.get_active(user_id, normalized)
        current_refs = {
            str(item["utc_date"]): item
            for item in (revision or {}).get("days", [])
        }
        conflicting_timestamps: set[int] = set()
        overlap_timestamps: set[int] = set()
        overlap_dates: set[str] = set()
        combined_candle_count = int((revision or {}).get("candle_count", 0))
        for utc_day, incoming in grouped.items():
            ref = current_refs.get(utc_day.isoformat())
            old_by_time = {}
            if not ref:
                old_by_time = {}
            else:
                old_result = self.snapshot_store.read_cached_candle_date(ref)
                old_by_time = {int(row["time_ms"]): row for row in old_result["candles"]}
            for row in incoming:
                previous = old_by_time.get(int(row["time_ms"]))
                if previous is not None:
                    overlap_timestamps.add(int(row["time_ms"]))
                    overlap_dates.add(source_date_for_time(int(row["time_ms"])).isoformat())
                    if any(previous.get(key) != row.get(key) for key in _CANDLE_FIELDS[1:]):
                        conflicting_timestamps.add(int(row["time_ms"]))
                else:
                    combined_candle_count += 1
        cached_dates = list((revision or {}).get("source_dates", []))
        merged_dates = sorted(set(cached_dates) | set(incoming_source_dates))
        conflict_dates = sorted(
            {source_date_for_time(stamp).isoformat() for stamp in conflicting_timestamps}
        )
        return {
            "instrument": normalized,
            "revision": str(revision["_id"]) if revision else None,
            "expected_revision": str(revision["_id"]) if revision else None,
            "cached_dates": cached_dates,
            "incoming_dates": incoming_source_dates,
            "available_dates": merged_dates,
            "candle_count": combined_candle_count,
            "overlap_count": len(overlap_timestamps),
            "conflict_count": len(conflicting_timestamps),
            "conflicting_dates": conflict_dates,
            "overlap_dates": sorted(overlap_dates),
            "requires_confirmation": bool(overlap_timestamps),
        }

    def merge(
        self,
        user_id,
        instrument: str,
        files: Iterable,
        *,
        expected_revision: str | None,
        confirm_overwrite: bool,
    ) -> dict:
        user_oid = _as_user_oid(user_id)
        normalized = instrument.strip().upper()
        grouped, incoming_source_dates = parse_histdata_files(files)
        current = self.get_active(user_oid, normalized)
        current_revision = str(current["_id"]) if current else None
        if current_revision != expected_revision:
            raise ConflictError(
                "The cached manual data changed. Refresh its coverage and submit the files again."
            )
        current_refs = {
            str(item["utc_date"]): item
            for item in (current or {}).get("days", [])
        }
        overlap_count = 0
        overlap_dates: set[str] = set()
        conflicts_by_date: set[str] = set()
        for utc_day, incoming in grouped.items():
            ref = current_refs.get(utc_day.isoformat())
            if not ref:
                continue
            old_rows = self.snapshot_store.read_cached_candle_date(ref)["candles"]
            old_by_time = {int(row["time_ms"]): row for row in old_rows}
            for row in incoming:
                stamp = int(row["time_ms"])
                previous = old_by_time.get(stamp)
                if previous is not None:
                    overlap_count += 1
                    overlap_dates.add(source_date_for_time(stamp).isoformat())
                    if any(previous.get(key) != row.get(key) for key in _CANDLE_FIELDS[1:]):
                        conflicts_by_date.add(source_date_for_time(stamp).isoformat())
        if overlap_count and not confirm_overwrite:
            raise ConflictError(
                "Uploaded timestamps overlap cached candles. Confirm that the files should be merged and differing cached candles replaced.",
                details={
                    "requires_confirmation": True,
                    "conflicting_dates": sorted(conflicts_by_date),
                    "affected_dates": sorted(overlap_dates),
                    "overlap_count": overlap_count,
                },
            )

        merged_days = dict(current_refs)
        total_candles = int((current or {}).get("candle_count", 0))
        for utc_day, incoming in grouped.items():
            day_key = utc_day.isoformat()
            ref = current_refs.get(day_key)
            old_rows = []
            old_by_time = {}
            if ref:
                old_rows = self.snapshot_store.read_cached_candle_date(ref)["candles"]
                old_by_time = {int(row["time_ms"]): row for row in old_rows}
            merged_by_time = dict(old_by_time)
            for row in incoming:
                stamp = int(row["time_ms"])
                merged_by_time[stamp] = row
            merged_rows = [merged_by_time[key] for key in sorted(merged_by_time)]
            if merged_rows == old_rows and ref:
                continue
            object_key, checksum, object_size = self.snapshot_store.write_cached_candle_date(
                user_oid,
                normalized,
                utc_day,
                merged_rows,
                cache_version=MANUAL_CANDLE_CACHE_VERSION,
            )
            merged_days[day_key] = {
                "source": "manual",
                "cache_version": MANUAL_CANDLE_CACHE_VERSION,
                "instrument": normalized,
                "utc_date": day_key,
                "object_key": object_key,
                "sha256": checksum,
                "object_size": object_size,
                "data_sha256": canonical_candle_checksum(merged_rows),
                "outcome": "data",
                "candle_count": len(merged_rows),
            }
            total_candles += len(merged_rows) - len(old_rows)

        revision_id = ObjectId()
        source_dates = sorted(
            set((current or {}).get("source_dates", [])) | set(incoming_source_dates)
        )
        revision = {
            "_id": revision_id,
            "user_id": user_oid,
            "instrument": normalized,
            "cache_version": MANUAL_CANDLE_CACHE_VERSION,
            "days": [merged_days[key] for key in sorted(merged_days)],
            "source_dates": source_dates,
            "candle_count": total_candles,
            "created_at": datetime.now(timezone.utc),
        }
        self.revisions.insert_one(revision)
        head_filter = {"user_id": user_oid, "instrument": normalized}
        if current is None:
            try:
                self.heads.insert_one({
                    **head_filter,
                    "revision_id": revision_id,
                    "updated_at": datetime.now(timezone.utc),
                })
            except DuplicateKeyError as exc:
                raise ConflictError(
                    "Another import updated this instrument. Refresh coverage and try again."
                ) from exc
        else:
            result = self.heads.update_one(
                {**head_filter, "revision_id": current["_id"]},
                {"$set": {"revision_id": revision_id, "updated_at": datetime.now(timezone.utc)}},
            )
            if result.modified_count != 1:
                raise ConflictError(
                    "Another import updated this instrument. Refresh coverage and try again."
                )
        return revision

    def get_day_ref(self, revision: dict, utc_date: date) -> dict:
        for ref in revision.get("days", []):
            if str(ref.get("utc_date")) == utc_date.isoformat():
                return dict(ref)
        return {
            "source": "manual",
            "cache_version": MANUAL_CANDLE_CACHE_VERSION,
            "instrument": revision["instrument"],
            "utc_date": utc_date.isoformat(),
            "object_key": None,
            "sha256": "empty",
            "data_sha256": canonical_candle_checksum([]),
            "object_size": 0,
            "outcome": "empty",
            "candle_count": 0,
        }

    def find_matching_ref(
        self, user_id, instrument: str, utc_date: str, data_sha256: str
    ) -> dict | None:
        user_oid = _as_user_oid(user_id)
        for revision in self.revisions.find({
            "user_id": user_oid,
            "instrument": instrument.strip().upper(),
            "days.utc_date": utc_date,
            "days.data_sha256": data_sha256,
        }):
            for ref in revision.get("days", []):
                if (
                    str(ref.get("utc_date")) == utc_date
                    and ref.get("data_sha256") == data_sha256
                    and ref.get("cache_version") == MANUAL_CANDLE_CACHE_VERSION
                ):
                    return dict(ref)
        return None
