"""Durable staged dates and immutable replay snapshot in MinIO."""

from __future__ import annotations

import hashlib
from bisect import bisect_right
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from io import BytesIO
import re

import pandas as pd
from minio.error import S3Error

from app.storage import (
    ensure_bucket_exists,
    get_client,
    get_market_data_bucket,
)
from app.utils.datetime_utils import utc_now


_CANDLE_COLUMNS = ("time_ms", "open", "high", "low", "close", "volume")
_FX_COLUMNS = ("time_ms", "open", "high", "low", "close")


class CachedCandleObjectMissing(RuntimeError):
    """Raised when a cache manifest points to a missing MinIO object."""


class CachedCandleObjectInvalid(RuntimeError):
    """Raised when a cached candle object fails its stored integrity checks."""


def _utc_midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _utc_day_start_ms(value: date) -> int:
    return int(_utc_midnight(value).timestamp() * 1000)


def _utc_day_end_ms(value: date) -> int:
    return _utc_day_start_ms(value + timedelta(days=1))


class SnapshotStore:
    """Store shared candle days and build run metadata over cache references."""

    def __init__(self, client=None, bucket: str | None = None):
        self.client = client
        self.bucket = bucket

    @property
    def _client(self):
        return self.client or get_client()

    @property
    def _bucket(self):
        return self.bucket or get_market_data_bucket()

    def write_staged_date(
        self,
        user_id,
        run_id,
        utc_date: date,
        candles: list[dict],
        *,
        before_write=None,
        after_write=None,
    ) -> str | None:
        if not candles:
            return None
        payload = self._parquet_bytes(candles)
        checksum = hashlib.sha256(payload).hexdigest()
        # A stale worker writes a distinct immutable key instead of replacing
        # the staged object referenced by a committed checkpoint.
        key = (
            f"backtests/{user_id}/{run_id}/staging/"
            f"{utc_date.isoformat()}/{checksum}.parquet"
        )
        if before_write is not None:
            before_write()
        self._put(key, payload)
        if after_write is not None:
            after_write(key)
        return key

    def write_staged_conversion_date(
        self,
        user_id,
        run_id,
        instrument: str,
        utc_date: date,
        candles: list[dict],
        *,
        before_write=None,
        after_write=None,
    ) -> str | None:
        """Stage one immutable conversion instrument date under its run namespace."""
        if not candles:
            return None
        payload = self._fx_parquet_bytes(candles)
        checksum = hashlib.sha256(payload).hexdigest()
        key = (
            f"backtests/{user_id}/{run_id}/staging/fx/"
            f"{instrument.upper()}/{utc_date.isoformat()}/{checksum}.parquet"
        )
        if before_write is not None:
            before_write()
        self._put(key, payload)
        if after_write is not None:
            after_write(key)
        return key

    def write_cached_candle_date(
        self,
        user_id,
        instrument: str,
        utc_date: date,
        candles: list[dict],
        *,
        cache_version: str,
    ) -> tuple[str, str, int]:
        """Write a reusable user-owned UTC day, including known-empty days."""
        payload = self._parquet_bytes(candles)
        checksum = hashlib.sha256(payload).hexdigest()
        safe_instrument = re.sub(r"[^A-Z0-9._-]", "_", instrument.upper())
        key = (
            f"backtests/{user_id}/shared-candles/{cache_version}/"
            f"{safe_instrument}/{utc_date.isoformat()}/{checksum}.parquet"
        )
        self._put(key, payload)
        return key, checksum, len(payload)

    def read_cached_candle_date(
        self, entry: dict, *, check_object_exists: bool = False
    ) -> dict:
        """Read and verify a normalized reusable candle date from MinIO."""
        object_key = entry.get("object_key")
        checksum = entry.get("sha256")
        candle_count = entry.get("candle_count")
        if (
            not isinstance(object_key, str)
            or not object_key
            or not isinstance(checksum, str)
            or isinstance(candle_count, bool)
            or not isinstance(candle_count, int)
            or candle_count < 0
        ):
            raise CachedCandleObjectInvalid("Cached candle reference is invalid.")
        try:
            if check_object_exists:
                self._check_cached_object_exists(object_key)
            frame = self._read_verified_cache_frame(
                object_key, checksum, candle_count
            )
        except KeyError as exc:
            raise CachedCandleObjectMissing(object_key) from exc
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchBucket", "NotFound"}:
                raise CachedCandleObjectMissing(object_key) from exc
            raise
        candles = frame.loc[:, list(_CANDLE_COLUMNS)].to_dict(orient="records")
        outcome = entry.get("outcome")
        if outcome not in {"data", "empty"} or (outcome == "data") != bool(candles):
            raise CachedCandleObjectInvalid("Cached candle outcome does not match.")
        try:
            utc_date = date.fromisoformat(str(entry["utc_date"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise CachedCandleObjectInvalid("Cached candle date is invalid.") from exc
        return {"utc_date": utc_date, "outcome": outcome, "candles": candles}

    def _check_cached_object_exists(self, object_key: str) -> None:
        """Check that a ready metadata hit still has its MinIO object."""
        try:
            self._client.stat_object(self._bucket, object_key)
        except KeyError as exc:
            # Keep lightweight test/object-store adapters compatible with the
            # MinIO missing-key behavior.
            raise CachedCandleObjectMissing(object_key) from exc
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchBucket", "NotFound"}:
                raise CachedCandleObjectMissing(object_key) from exc
            raise

    @lru_cache(maxsize=64)
    def _read_verified_cache_frame(
        self, object_key: str, checksum: str, candle_count: int
    ) -> pd.DataFrame:
        """Read one content-addressed cache day once per worker process."""
        payload = self._read_bytes(object_key)
        if hashlib.sha256(payload).hexdigest() != checksum:
            raise CachedCandleObjectInvalid("Cached candle checksum does not match.")
        try:
            frame = pd.read_parquet(BytesIO(payload))
        except Exception as exc:
            raise CachedCandleObjectInvalid(
                "Cached candle Parquet is invalid."
            ) from exc
        if not set(_CANDLE_COLUMNS).issubset(frame.columns):
            raise CachedCandleObjectInvalid("Cached candle columns are incomplete.")
        if len(frame.index) != candle_count:
            raise CachedCandleObjectInvalid("Cached candle row count does not match.")
        return frame.loc[:, list(_CANDLE_COLUMNS)].reset_index(drop=True)

    def cached_candle_ref_exists(self, ref: dict) -> bool:
        """Check whether a cache object referenced by a run is still present."""
        try:
            self.read_cached_candle_date(ref)
        except (CachedCandleObjectMissing, CachedCandleObjectInvalid):
            return False
        return True

    def clear_cached_candle_reads(self) -> None:
        """Discard process-local frames before checking shared-cache health."""
        self._read_verified_cache_frame.cache_clear()

    def assemble_cache_snapshot(
        self,
        *,
        run: dict,
        completed_dates: list[dict],
        fx_conversion: dict | None = None,
        cache_version: str,
    ) -> tuple[dict, dict]:
        """Build replay indexes and coverage using shared cached date objects.

        The run stores only cache references and small per-day index metadata;
        candle bytes remain in the per-user shared cache.
        """
        context_start_ms = int(
            run.get("context_start_utc_ms", run["start_utc_ms"])
        )
        end_ms = int(run["end_utc_ms"])
        start_ms = int(run["start_utc_ms"])
        ordered = sorted(
            completed_dates,
            key=lambda item: _as_date(item["utc_date"]),
        )
        frames: list[pd.DataFrame] = []
        indexes: list[dict] = []
        empty_dates: list[date] = []
        available_dates: list[date] = []
        next_source_index = 0
        for checkpoint in ordered:
            ref = checkpoint.get("cache_ref")
            if not isinstance(ref, dict):
                raise CachedCandleObjectInvalid(
                    "A run preparation checkpoint has no shared-cache reference."
                )
            result = self.read_cached_candle_date(ref)
            utc_date = _as_date(checkpoint["utc_date"])
            if result["utc_date"] != utc_date:
                raise CachedCandleObjectInvalid(
                    "A shared-cache reference points to a different UTC date."
                )
            frame = pd.DataFrame(
                result["candles"], columns=list(_CANDLE_COLUMNS)
            )
            if not frame.empty:
                frame = frame[
                    (frame["time_ms"] >= context_start_ms)
                    & (frame["time_ms"] < end_ms)
                ].sort_values("time_ms", kind="stable")
            count = len(frame.index)
            indexes.append(
                {
                    "utc_date": utc_date.isoformat(),
                    "first_source_candle_index": next_source_index,
                    "candle_count": count,
                    "first_time_ms": int(frame.iloc[0]["time_ms"]) if count else None,
                    "last_time_ms": int(frame.iloc[-1]["time_ms"]) if count else None,
                    "cache_ref": ref,
                }
            )
            next_source_index += count
            if count:
                frames.append(frame)
                available_dates.append(utc_date)
            elif (
                result["outcome"] == "empty"
                or _utc_day_end_ms(utc_date) > context_start_ms
                and _utc_day_start_ms(utc_date) < end_ms
            ):
                empty_dates.append(utc_date)

        frame = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=list(_CANDLE_COLUMNS))
        )
        if not frame.empty:
            frame = (
                frame.drop_duplicates(subset=["time_ms"], keep="first")
                .sort_values("time_ms", kind="stable")
                .reset_index(drop=True)
            )
        replay_frame = frame[frame["time_ms"] >= start_ms].reset_index(drop=True)
        warmup_frame = frame[frame["time_ms"] < start_ms].reset_index(drop=True)
        replay_start_source_index = len(warmup_frame.index)
        replay_start_time_ms = (
            int(replay_frame.iloc[0]["time_ms"]) if not replay_frame.empty else None
        )
        selected_empty_dates = [
            day for day in empty_dates
            if _utc_day_end_ms(day) > start_ms and _utc_day_start_ms(day) < end_ms
        ]
        warmup_empty_dates = [
            day for day in empty_dates
            if _utc_day_end_ms(day) > context_start_ms
            and _utc_day_start_ms(day) < start_ms
        ]
        replay_gaps = self._partial_gaps(replay_frame)
        warmup_gaps = self._partial_gaps(warmup_frame)
        coverage = self._coverage(replay_frame, selected_empty_dates, replay_gaps)
        warmup_coverage = self._coverage(
            warmup_frame, warmup_empty_dates, warmup_gaps
        )
        time_values = [int(value) for value in frame["time_ms"].tolist()]
        snapshot = {
            "storage_mode": "shared_cache",
            "cache_version": cache_version,
            "instrument": run["instrument"],
            "source_side": run.get("source_side", "COMB"),
            "price_mode": run.get("price_mode", "combined_midpoint"),
            "volume_semantics": run.get(
                "volume_semantics", "two_sided_quote_liquidity"
            ),
            "interval_minutes": 1,
            "candle_count": len(frame.index),
            "context_start_utc_ms": context_start_ms,
            "end_utc_ms": end_ms,
            "replay_start_source_index": replay_start_source_index,
            "replay_start_time_ms": replay_start_time_ms,
            "_normalization_reference_price": (
                float(replay_frame.iloc[0]["open"])
                if not replay_frame.empty
                else None
            ),
            "replay_period_candle_count": len(replay_frame.index),
            "warmup_coverage": warmup_coverage,
            "first_time_ms": time_values[0] if time_values else None,
            "last_time_ms": time_values[-1] if time_values else None,
            "available_utc_dates": [
                _utc_midnight(day) for day in sorted(set(available_dates))
            ],
            "_day_candle_indexes": indexes,
            "gap_dates": [_utc_midnight(day) for day in selected_empty_dates],
            "warmup_gap_dates": [_utc_midnight(day) for day in warmup_empty_dates],
            "partial_gap_summary": replay_gaps,
            "fetched_at": utc_now(),
        }
        fx_series = self._build_cache_fx_conversion_series(
            run=run, conversion=fx_conversion
        )
        if fx_series:
            snapshot["fx_conversion_series"] = fx_series
        return snapshot, coverage

    def assemble_snapshot(
        self,
        *,
        user_id,
        run: dict,
        completed_dates: list[dict],
        fx_conversion: dict | None = None,
        before_publish=None,
        after_publish=None,
    ) -> tuple[dict, dict]:
        frames = []
        for checkpoint in completed_dates:
            object_key = checkpoint.get("object_key")
            if object_key:
                frames.append(self._read_parquet(object_key))
        if not frames:
            return self._empty_result(completed_dates)

        frame = pd.concat(frames, ignore_index=True)
        frame = frame.drop_duplicates(subset=["time_ms"], keep="first")
        frame = frame.sort_values("time_ms", kind="stable")
        frame = frame[
            (frame["time_ms"] >= int(run.get("context_start_utc_ms", run["start_utc_ms"])))
            & (frame["time_ms"] < int(run["end_utc_ms"]))
        ].reset_index(drop=True)
        if frame.empty:
            return self._empty_result(completed_dates)

        frame = frame.loc[:, list(_CANDLE_COLUMNS)]
        candles = frame.to_dict(orient="records")
        payload = self._parquet_bytes(candles)
        checksum = hashlib.sha256(payload).hexdigest()
        run_id = run["_id"]
        # Content-addressing makes a stale lease holder unable to replace a
        # different snapshot after a new worker publishes its own artifact.
        object_key = (
            f"backtests/{user_id}/{run_id}/snapshot/{checksum}.parquet"
        )

        time_values = [int(value) for value in frame["time_ms"].tolist()]
        day_indexes = self._write_snapshot_days(
            user_id=user_id,
            run_id=run_id,
            snapshot_checksum=checksum,
            frame=frame,
            time_values=time_values,
            before_write=before_publish,
            after_write=after_publish,
        )
        if before_publish is not None:
            before_publish()
        self._put(object_key, payload)
        if after_publish is not None:
            after_publish(object_key)

        replay_start_ms = int(run["start_utc_ms"])
        replay_frame = frame[frame["time_ms"] >= replay_start_ms].reset_index(drop=True)
        warmup_frame = frame[frame["time_ms"] < replay_start_ms].reset_index(drop=True)
        replay_start_source_index = len(warmup_frame.index)
        replay_start_time_ms = (
            int(replay_frame.iloc[0]["time_ms"]) if not replay_frame.empty else None
        )
        available_dates = sorted(
            {
                datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()
                for value in time_values
            }
        )
        empty_dates = sorted(
            {
                _as_date(item["utc_date"])
                for item in completed_dates
                if item.get("outcome") == "empty"
                and _as_date(item["utc_date"]) not in set(available_dates)
            }
        )
        selected_empty_dates = [
            value for value in empty_dates
            if (_utc_day_end_ms(value) > replay_start_ms)
            and (_utc_day_start_ms(value) < int(run["end_utc_ms"]))
        ]
        warmup_end_ms = replay_start_ms
        context_start_ms = int(run.get("context_start_utc_ms", replay_start_ms))
        warmup_empty_dates = [
            value for value in empty_dates
            if (_utc_day_end_ms(value) > context_start_ms)
            and (_utc_day_start_ms(value) < warmup_end_ms)
        ]
        gap_summary = self._partial_gaps(replay_frame)
        warmup_gap_summary = self._partial_gaps(warmup_frame)
        coverage = self._coverage(replay_frame, selected_empty_dates, gap_summary)
        warmup_coverage = self._coverage(
            warmup_frame, warmup_empty_dates, warmup_gap_summary
        )
        fx_series = self._assemble_fx_conversion(
            user_id=user_id,
            run_id=run_id,
            run=run,
            conversion=fx_conversion,
            before_publish=before_publish,
            after_publish=after_publish,
        )
        fetched_at = utc_now()
        snapshot = {
            "object_key": object_key,
            "sha256": checksum,
            "instrument": run["instrument"],
            "source_side": run.get("source_side", "COMB"),
            "price_mode": run.get("price_mode", "combined_midpoint"),
            "volume_semantics": run.get(
                "volume_semantics", "two_sided_quote_liquidity"
            ),
            "interval_minutes": 1,
            "candle_count": len(frame.index),
            "context_start_utc_ms": context_start_ms,
            "replay_start_source_index": replay_start_source_index,
            "replay_start_time_ms": replay_start_time_ms,
            # The worker consumes this internal handoff before persisting the
            # public snapshot metadata or serializing the run response.
            "_normalization_reference_price": (
                float(replay_frame.iloc[0]["open"])
                if not replay_frame.empty
                else None
            ),
            "replay_period_candle_count": len(replay_frame.index),
            "warmup_coverage": warmup_coverage,
            "first_time_ms": time_values[0],
            "last_time_ms": time_values[-1],
            "available_utc_dates": [_utc_midnight(value) for value in available_dates],
            # Internal range index maps global source-candle indexes to one
            # immutable UTC-day Parquet partition. It stays out of API JSON.
            "_day_candle_indexes": day_indexes,
            "gap_dates": [_utc_midnight(value) for value in selected_empty_dates],
            "warmup_gap_dates": [
                _utc_midnight(value) for value in warmup_empty_dates
            ],
            "partial_gap_summary": gap_summary,
            "fetched_at": fetched_at,
        }
        if fx_series:
            snapshot["fx_conversion_series"] = fx_series
        return snapshot, coverage

    def read_snapshot(self, object_key: str) -> pd.DataFrame:
        return self._read_parquet(object_key)

    def read_fx_conversion_series(
        self, snapshot: dict, instrument_or_quote: str
    ) -> list[dict]:
        """Read pinned one-minute observations by instrument, or legacy quote."""
        key = str(instrument_or_quote).strip().upper()
        ref = next(
            (
                item
                for item in snapshot.get("fx_conversion_series", [])
                if str(item.get("instrument", "")).upper() == key
            ),
            None,
        )
        if ref is None:
            ref = next(
                (
                    item
                    for item in snapshot.get("fx_conversion_series", [])
                    if str(item.get("quote_currency", "")).upper() == key
                ),
                None,
        )
        if not ref:
            return []
        cache_refs = ref.get("_cache_date_refs")
        if isinstance(cache_refs, list):
            frames = []
            for cache_ref in cache_refs:
                candles = self.read_cached_candle_date(cache_ref)["candles"]
                if candles:
                    frames.append(
                        pd.DataFrame(candles, columns=list(_CANDLE_COLUMNS))
                    )
            if not frames:
                return []
            frame = pd.concat(frames, ignore_index=True)
            frame = (
                frame.drop_duplicates(subset=["time_ms"], keep="first")
                .sort_values("time_ms", kind="stable")
            )
            start_ms = int(ref["source_start_utc_ms"])
            end_ms = int(ref["source_end_utc_ms"])
            frame = frame[
                (frame["time_ms"] >= start_ms)
                & (frame["time_ms"] < end_ms)
            ]
            return frame.loc[:, list(_FX_COLUMNS)].to_dict(orient="records")
        if not ref.get("object_key"):
            return []
        frame = self._read_parquet(
            ref["object_key"], columns=list(_FX_COLUMNS)
        ).sort_values("time_ms", kind="stable")
        return frame.to_dict(orient="records")

    def read_snapshot_day(self, snapshot: dict, utc_date: str) -> pd.DataFrame:
        """Read a UTC-day partition through its shared cache reference."""
        indexes = snapshot.get("_day_candle_indexes")
        if isinstance(indexes, list):
            entry = next(
                (
                    item
                    for item in indexes
                    if item.get("utc_date") == utc_date
                ),
                None,
            )
            if entry is None:
                return pd.DataFrame(columns=list(_CANDLE_COLUMNS))
            cache_ref = entry.get("cache_ref")
            if isinstance(cache_ref, dict):
                result = self.read_cached_candle_date(cache_ref)
                frame = pd.DataFrame(
                    result["candles"], columns=list(_CANDLE_COLUMNS)
                ).sort_values("time_ms", kind="stable")
                if not frame.empty:
                    frame = frame[
                        (frame["time_ms"] >= int(snapshot.get("context_start_utc_ms", 0)))
                        & (frame["time_ms"] < int(snapshot.get("end_utc_ms", 2**63 - 1)))
                    ]
                return frame
            return self._read_parquet(entry["object_key"])

        # Snapshots created before day partitions were introduced remain
        # readable, though newly assembled snapshots always take the fast path.
        frame = self.read_snapshot(snapshot["object_key"])
        day = date.fromisoformat(utc_date)
        day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        day_end = day_start + pd.Timedelta(days=1)
        start_ms = int(day_start.timestamp() * 1000)
        end_ms = int(day_end.timestamp() * 1000)
        return frame[
            (frame["time_ms"] >= start_ms)
            & (frame["time_ms"] < end_ms)
        ].sort_values("time_ms", kind="stable")

    def read_snapshot_candle_time(
        self, snapshot: dict, source_candle_index: int
    ) -> int | None:
        """Resolve a global source index through its shared cache date."""
        indexes = snapshot.get("_day_candle_indexes")
        if isinstance(indexes, list):
            for entry in indexes:
                first = int(entry["first_source_candle_index"])
                count = int(entry["candle_count"])
                if first <= source_candle_index < first + count:
                    relative_index = source_candle_index - first
                    cache_ref = entry.get("cache_ref")
                    if isinstance(cache_ref, dict):
                        times = tuple(
                            int(value)
                            for value in self.read_snapshot_day(
                                snapshot, entry["utc_date"]
                            )["time_ms"].tolist()
                        )
                        if relative_index >= len(times):
                            return None
                        return times[relative_index]
                    times = self._read_day_time_index(entry["object_key"])
                    if relative_index >= len(times):
                        return None
                    return times[relative_index]
            return None

        # Legacy snapshots have no range index. Keep compatibility while
        # avoiding loading price/volume columns for this uncommon fallback.
        times = self._read_parquet(
            snapshot["object_key"], columns=["time_ms"]
        )["time_ms"].tolist()
        if source_candle_index >= len(times):
            return None
        return int(times[source_candle_index])

    def source_index_at_or_before(self, snapshot: dict, time_ms: int) -> int | None:
        """Return the latest source index whose candle time is <= the given time."""
        indexes = snapshot.get("_day_candle_indexes")
        if not isinstance(indexes, list):
            return None
        last_candidate = None
        for entry in reversed(indexes):
            count = int(entry.get("candle_count", 0))
            last_time = entry.get("last_time_ms")
            if count < 1 or last_time is None:
                continue
            if int(last_time) <= time_ms:
                last_candidate = (
                    int(entry["first_source_candle_index"]) + count - 1
                )
                break
            first_time = entry.get("first_time_ms")
            if first_time is None or int(first_time) > time_ms:
                continue
            frame = self.read_snapshot_day(snapshot, entry["utc_date"])
            times = [int(value) for value in frame["time_ms"].tolist()]
            index = bisect_right(times, time_ms) - 1
            if index >= 0:
                return int(entry["first_source_candle_index"]) + index
        return last_candidate

    def source_index_after_time(self, snapshot: dict, time_ms: int) -> int | None:
        """Return the first source index whose candle time is strictly later."""
        indexes = snapshot.get("_day_candle_indexes")
        if not isinstance(indexes, list):
            return None
        for entry in indexes:
            count = int(entry.get("candle_count", 0))
            first_time = entry.get("first_time_ms")
            last_time = entry.get("last_time_ms")
            if (
                count < 1
                or first_time is None
                or last_time is None
                or int(last_time) <= time_ms
            ):
                continue
            frame = self.read_snapshot_day(snapshot, entry["utc_date"])
            times = [int(value) for value in frame["time_ms"].tolist()]
            index = bisect_right(times, time_ms)
            if index < len(times):
                return int(entry["first_source_candle_index"]) + index
        return None

    def remove_prefix(self, prefix: str) -> None:
        client = self._client
        bucket = self._bucket
        for item in client.list_objects(bucket, prefix=prefix, recursive=True):
            client.remove_object(bucket, item.object_name)
        remaining = list(
            client.list_objects(bucket, prefix=prefix, recursive=True)
        )
        if remaining:
            raise RuntimeError(
                f"MinIO prefix cleanup left objects under {prefix}."
            )

    def remove_run_objects(self, user_id, run_id) -> None:
        self.remove_prefix(f"backtests/{user_id}/{run_id}/")

    def remove_object(self, object_key: str) -> None:
        self._client.remove_object(self._bucket, object_key)

    def _read_parquet(
        self, object_key: str, *, columns: list[str] | None = None
    ) -> pd.DataFrame:
        payload = self._read_bytes(object_key)
        return pd.read_parquet(BytesIO(payload), columns=columns)

    def _read_bytes(self, object_key: str) -> bytes:
        response = self._client.get_object(self._bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            release_conn = getattr(response, "release_conn", None)
            if release_conn is not None:
                release_conn()

    def _put(self, object_key: str, payload: bytes) -> None:
        client = self._client
        try:
            self._put_bytes(client, object_key, payload)
        except S3Error as exc:
            if exc.code != "NoSuchBucket":
                raise
            # The MinIO volume may have been replaced while the API process
            # remained alive, so startup bucket initialization is insufficient.
            ensure_bucket_exists(client, self._bucket)
            self._put_bytes(client, object_key, payload)

    def _put_bytes(self, client, object_key: str, payload: bytes) -> None:
        client.put_object(
            self._bucket,
            object_key,
            BytesIO(payload),
            len(payload),
            content_type="application/vnd.apache.parquet",
        )

    @staticmethod
    def _parquet_bytes(candles: list[dict]) -> bytes:
        frame = pd.DataFrame(candles, columns=list(_CANDLE_COLUMNS))
        buffer = BytesIO()
        frame.to_parquet(buffer, index=False)
        return buffer.getvalue()

    @staticmethod
    def _fx_parquet_bytes(candles: list[dict]) -> bytes:
        frame = pd.DataFrame(candles, columns=list(_FX_COLUMNS))
        buffer = BytesIO()
        frame.to_parquet(buffer, index=False)
        return buffer.getvalue()

    def _assemble_fx_conversion(
        self,
        *,
        user_id,
        run_id,
        run: dict,
        conversion: dict | None,
        before_publish=None,
        after_publish=None,
    ) -> list[dict]:
        """Publish content-addressed series for each frozen route instrument."""
        if not conversion:
            return []
        currency = str(conversion.get("quote_currency", "")).upper()
        if not currency or conversion.get("supported") is False:
            return []
        route = conversion.get("route")
        if not isinstance(route, list):
            route = (
                [{
                    "instrument": conversion.get("instrument"),
                    "direction": conversion.get("direction"),
                }]
                if conversion.get("instrument")
                and conversion.get("direction") in {"direct", "inverse"}
                else []
            )

        series = []
        for leg in route:
            if not isinstance(leg, dict) or not leg.get("instrument"):
                continue
            instrument = str(leg["instrument"]).upper()
            frames = []
            for checkpoint in conversion.get("completed_utc_dates", []):
                object_keys = checkpoint.get("object_keys")
                object_key = (
                    object_keys.get(instrument)
                    if isinstance(object_keys, dict)
                    else None
                )
                # Older workers stored one object_key keyed by quote currency.
                if not object_key and str(
                    checkpoint.get("instrument", conversion.get("instrument", ""))
                ).upper() == instrument:
                    object_key = checkpoint.get("object_key")
                if object_key:
                    frames.append(
                        self._read_parquet(object_key, columns=list(_FX_COLUMNS))
                    )
            if frames:
                frame = pd.concat(frames, ignore_index=True)
                frame = frame.drop_duplicates(subset=["time_ms"], keep="first")
                frame = frame.sort_values("time_ms", kind="stable")
                frame = frame[
                    (frame["time_ms"] >= int(run.get("context_start_utc_ms", run["start_utc_ms"])))
                    & (frame["time_ms"] < int(run["end_utc_ms"]))
                ].reset_index(drop=True)
            else:
                frame = pd.DataFrame(columns=list(_FX_COLUMNS))

            payload = self._fx_parquet_bytes(frame.to_dict(orient="records"))
            checksum = hashlib.sha256(payload).hexdigest()
            object_key = (
                f"backtests/{user_id}/{run_id}/snapshot/fx/"
                f"{instrument}/{checksum}.parquet"
            )
            if before_publish is not None:
                before_publish()
            self._put(object_key, payload)
            if after_publish is not None:
                after_publish(object_key)

            times = [int(value) for value in frame["time_ms"].tolist()]
            series.append({
                "quote_currency": currency,
                "instrument": instrument,
                "direction": leg.get("direction"),
                "from_currency": leg.get("from_currency"),
                "to_currency": leg.get("to_currency"),
                "interval_minutes": 1,
                "source_start_utc_ms": int(
                    run.get("context_start_utc_ms", run["start_utc_ms"])
                ),
                "source_end_utc_ms": int(run["end_utc_ms"]),
                "source_first_time_ms": times[0] if times else None,
                "source_last_time_ms": times[-1] if times else None,
                "candle_count": len(times),
                "object_key": object_key,
            })
        return series

    def _build_cache_fx_conversion_series(
        self, *, run: dict, conversion: dict | None
    ) -> list[dict]:
        """Describe frozen conversion inputs using shared per-day cache refs."""
        if not conversion:
            return []
        currency = str(conversion.get("quote_currency", "")).upper()
        if not currency or conversion.get("supported") is False:
            return []
        route = conversion.get("route")
        if not isinstance(route, list):
            route = (
                [{
                    "instrument": conversion.get("instrument"),
                    "direction": conversion.get("direction"),
                }]
                if conversion.get("instrument")
                and conversion.get("direction") in {"direct", "inverse"}
                else []
            )
        start_ms = int(run.get("context_start_utc_ms", run["start_utc_ms"]))
        end_ms = int(run["end_utc_ms"])
        series = []
        for leg in route:
            if not isinstance(leg, dict) or not leg.get("instrument"):
                continue
            instrument = str(leg["instrument"]).upper()
            cache_refs = []
            first_time_ms = None
            last_time_ms = None
            candle_count = 0
            for checkpoint in conversion.get("completed_utc_dates", []):
                refs = checkpoint.get("cache_refs")
                cache_ref = refs.get(instrument) if isinstance(refs, dict) else None
                if not isinstance(cache_ref, dict):
                    continue
                cache_refs.append(cache_ref)
                candles = self.read_cached_candle_date(cache_ref)["candles"]
                times = [
                    int(candle["time_ms"])
                    for candle in candles
                    if start_ms <= int(candle["time_ms"]) < end_ms
                ]
                if times:
                    candle_count += len(times)
                    if first_time_ms is None:
                        first_time_ms = times[0]
                    last_time_ms = times[-1]
            series.append({
                "quote_currency": currency,
                "instrument": instrument,
                "direction": leg.get("direction"),
                "from_currency": leg.get("from_currency"),
                "to_currency": leg.get("to_currency"),
                "interval_minutes": 1,
                "source_start_utc_ms": start_ms,
                "source_end_utc_ms": end_ms,
                "source_first_time_ms": first_time_ms,
                "source_last_time_ms": last_time_ms,
                "candle_count": candle_count,
                "_cache_date_refs": cache_refs,
            })
        return series

    def _write_snapshot_days(
        self,
        *,
        user_id,
        run_id,
        snapshot_checksum: str,
        frame: pd.DataFrame,
        time_values: list[int],
        before_write=None,
        after_write=None,
    ) -> list[dict]:
        """Write immutable UTC-day partitions and their global row ranges."""
        indexes = []
        start = 0
        while start < len(time_values):
            utc_date = datetime.fromtimestamp(
                time_values[start] / 1000, tz=timezone.utc
            ).date()
            stop = start + 1
            while stop < len(time_values):
                next_date = datetime.fromtimestamp(
                    time_values[stop] / 1000, tz=timezone.utc
                ).date()
                if next_date != utc_date:
                    break
                stop += 1
            partition = frame.iloc[start:stop]
            partition_payload = self._parquet_bytes(
                partition.to_dict(orient="records")
            )
            partition_checksum = hashlib.sha256(partition_payload).hexdigest()
            partition_key = (
                f"backtests/{user_id}/{run_id}/snapshot/"
                f"{snapshot_checksum}/days/{utc_date.isoformat()}/"
                f"{partition_checksum}.parquet"
            )
            if before_write is not None:
                before_write()
            self._put(partition_key, partition_payload)
            if after_write is not None:
                after_write(partition_key)
            indexes.append(
                {
                    "utc_date": utc_date.isoformat(),
                    "first_source_candle_index": start,
                    "candle_count": stop - start,
                    "object_key": partition_key,
                }
            )
            start = stop
        return indexes

    @lru_cache(maxsize=32)
    def _read_day_time_index(self, object_key: str) -> tuple[int, ...]:
        """Cache only one-day timestamps so cursor writes stay lightweight."""
        frame = self._read_parquet(object_key, columns=["time_ms"])
        return tuple(int(value) for value in frame["time_ms"].tolist())

    @staticmethod
    def _empty_result(completed_dates: list[dict]) -> tuple[dict, dict]:
        empty_dates = sorted(
            {_as_date(item["utc_date"]) for item in completed_dates}
        )
        gap_dates = [_utc_midnight(value) for value in empty_dates]
        return (
            {
                "gap_dates": gap_dates,
                "candle_count": 0,
                "replay_period_candle_count": 0,
                "replay_start_source_index": 0,
                "replay_start_time_ms": None,
                "warmup_coverage": {
                    "first_time_ms": None,
                    "last_time_ms": None,
                    "candle_count": 0,
                    "available_utc_dates": [],
                    "empty_utc_dates": gap_dates,
                    "partial_gaps": {
                        "gap_count": 0,
                        "missing_minutes": 0,
                        "longest_gap_minutes": None,
                        "examples": [],
                    },
                },
                "partial_gap_summary": {
                    "gap_count": 0,
                    "missing_minutes": 0,
                    "longest_gap_minutes": None,
                    "examples": [],
                },
            },
            {
                "first_time_ms": None,
                "last_time_ms": None,
                "candle_count": 0,
                "available_utc_dates": [],
                "empty_utc_dates": gap_dates,
                "partial_gaps": {
                    "gap_count": 0,
                    "missing_minutes": 0,
                    "longest_gap_minutes": None,
                    "examples": [],
                },
            },
        )

    @staticmethod
    def _coverage(frame: pd.DataFrame, empty_dates: list[date], gaps: dict) -> dict:
        times = [int(value) for value in frame["time_ms"].tolist()]
        available_dates = sorted(
            {
                datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()
                for value in times
            }
        )
        return {
            "first_time_ms": times[0] if times else None,
            "last_time_ms": times[-1] if times else None,
            "candle_count": len(times),
            "available_utc_dates": [_utc_midnight(value) for value in available_dates],
            "empty_utc_dates": [_utc_midnight(value) for value in empty_dates],
            "partial_gaps": gaps,
        }

    @staticmethod
    def _partial_gaps(frame: pd.DataFrame) -> dict:
        times = [int(value) for value in frame["time_ms"].tolist()]
        examples = []
        missing_total = 0
        longest = 0
        gap_count = 0
        for previous, current in zip(times, times[1:]):
            if current - previous <= 60_000:
                continue
            previous_date = datetime.fromtimestamp(
                previous / 1000, tz=timezone.utc
            ).date()
            current_date = datetime.fromtimestamp(
                current / 1000, tz=timezone.utc
            ).date()
            # Day boundaries are separate coverage days, not partial-day gaps.
            if previous_date != current_date:
                continue
            missing = max(0, (current - previous) // 60_000 - 1)
            if not missing:
                continue
            gap_count += 1
            missing_total += missing
            longest = max(longest, missing)
            if len(examples) < 20:
                examples.append(
                    {
                        "start_time_ms": previous + 60_000,
                        "end_time_ms": current,
                        "missing_minutes": missing,
                    }
                )
        return {
            "gap_count": gap_count,
            "missing_minutes": missing_total,
            "longest_gap_minutes": longest or None,
            "examples": examples,
        }


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
