"""Per-user MinIO cache for normalized Dukascopy candle days."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import threading
import time
import uuid

from bson import ObjectId
from flask import current_app, has_app_context
from pymongo.errors import DuplicateKeyError

from app.backtests.snapshot_store import (
    CachedCandleObjectInvalid,
    CachedCandleObjectMissing,
    SnapshotStore,
)
from app.extensions import mongo
from app.utils.datetime_utils import utc_now


CANDLE_CACHE_VERSION = "dukascopy-comb-1m-v1"
_DEFAULT_LEASE_SECONDS = 900
_DEFAULT_POLL_SECONDS = 0.1


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class CandleCacheLeaseLost(RuntimeError):
    """Raised when another worker takes ownership of a cache miss."""


class _CacheLeaseHeartbeat:
    """Keep a per-day download claim alive while its provider call runs."""

    def __init__(
        self,
        *,
        identity: dict,
        owner: str,
        lease_seconds: int,
        clock,
    ):
        if not has_app_context():
            raise RuntimeError("Candle cache access requires an app context.")
        self.app = current_app._get_current_object()
        self.identity = identity
        self.owner = owner
        self.lease_seconds = lease_seconds
        self.clock = clock
        self.stop_event = threading.Event()
        self.lost = threading.Event()
        interval = max(0.1, min(30.0, lease_seconds / 3))
        self.thread = threading.Thread(
            target=self._run,
            args=(interval,),
            name=f"backtest-candle-cache-{owner[:8]}",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def check(self) -> None:
        if self.lost.is_set():
            raise CandleCacheLeaseLost("Candle cache download lease was lost.")

    def _run(self, interval: float) -> None:
        while not self.stop_event.wait(interval):
            try:
                with self.app.app_context():
                    result = mongo.db.backtest_candle_cache.update_one(
                        {
                            **self.identity,
                            "state": "loading",
                            "lease_owner": self.owner,
                        },
                        {
                            "$set": {
                                "lease_expires_at": _as_utc(self.clock())
                                + timedelta(seconds=self.lease_seconds),
                                "updated_at": _as_utc(self.clock()),
                            }
                        },
                    )
                if result.matched_count != 1:
                    self.lost.set()
                    return
            except Exception:
                # A transient Mongo failure may recover on the next renewal.
                continue


class BacktestCandleCache:
    """Share one validated, immutable UTC candle day across a user's runs."""

    def __init__(
        self,
        *,
        snapshot_store: SnapshotStore | None = None,
        clock=None,
        lease_seconds: int = _DEFAULT_LEASE_SECONDS,
        poll_seconds: float = _DEFAULT_POLL_SECONDS,
    ):
        self.snapshot_store = snapshot_store or SnapshotStore()
        self.clock = clock or utc_now
        self.lease_seconds = max(1, int(lease_seconds))
        self.poll_seconds = max(0.01, float(poll_seconds))

    @property
    def collection(self):
        return mongo.db.backtest_candle_cache

    @property
    def cache_version(self) -> str:
        return CANDLE_CACHE_VERSION

    def get_or_fetch(
        self,
        *,
        user_id,
        instrument: str,
        utc_date: date,
        fetcher,
        check_wait=None,
    ) -> dict:
        """Return a cached day or fetch it once under a Mongo lease."""
        user_oid = user_id if isinstance(user_id, ObjectId) else ObjectId(str(user_id))
        normalized_instrument = str(instrument).strip().upper()
        if not normalized_instrument:
            raise ValueError("Candle cache instrument is required.")
        if not isinstance(utc_date, date) or isinstance(utc_date, datetime):
            raise ValueError("Candle cache date must be a UTC date.")
        identity = {
            "user_id": user_oid,
            "cache_key": (
                f"{CANDLE_CACHE_VERSION}:{normalized_instrument}:"
                f"{utc_date.isoformat()}"
            ),
        }

        while True:
            if check_wait is not None:
                check_wait()
            now = _as_utc(self.clock())
            entry = self.collection.find_one(identity)
            if entry is not None and entry.get("state") == "ready":
                try:
                    # The process-local frame LRU can outlive a deleted or
                    # recreated MinIO volume. Check the content-addressed
                    # object still exists before trusting the cached frame.
                    return self.snapshot_store.read_cached_candle_date(
                        entry, check_object_exists=True
                    )
                except (CachedCandleObjectMissing, CachedCandleObjectInvalid) as exc:
                    self.collection.update_one(
                        {
                            **identity,
                            "state": "ready",
                            "object_key": entry.get("object_key"),
                        },
                        {
                            "$set": {
                                "state": "failed",
                                "last_error_type": type(exc).__name__,
                                "updated_at": now,
                            },
                            "$unset": {
                                "lease_owner": "",
                                "lease_expires_at": "",
                            },
                        },
                    )
                    continue

            owner = uuid.uuid4().hex
            if entry is None:
                document = {
                    **identity,
                    "_id": ObjectId(),
                    "instrument": normalized_instrument,
                    "utc_date": utc_date.isoformat(),
                    "cache_version": CANDLE_CACHE_VERSION,
                    "state": "loading",
                    "lease_owner": owner,
                    "lease_expires_at": now
                    + timedelta(seconds=self.lease_seconds),
                    "created_at": now,
                    "updated_at": now,
                }
                try:
                    self.collection.insert_one(document)
                except DuplicateKeyError:
                    continue
                return self._fetch_and_publish(
                    document,
                    owner=owner,
                    utc_date=utc_date,
                    fetcher=fetcher,
                )

            if (
                entry.get("state") == "loading"
                and entry.get("lease_expires_at") is not None
                and _as_utc(entry["lease_expires_at"]) > now
            ):
                time.sleep(self.poll_seconds)
                continue

            claim_filter = {
                "_id": entry["_id"],
                "state": entry.get("state"),
            }
            if entry.get("state") == "loading":
                claim_filter["lease_owner"] = entry.get("lease_owner")
                claim_filter["lease_expires_at"] = entry.get("lease_expires_at")
            claimed = self.collection.update_one(
                claim_filter,
                {
                    "$set": {
                        "state": "loading",
                        "lease_owner": owner,
                        "lease_expires_at": now
                        + timedelta(seconds=self.lease_seconds),
                        "updated_at": now,
                    },
                    "$unset": {"last_error_type": ""},
                },
            )
            if claimed.modified_count != 1:
                continue
            entry.update(
                {
                    "state": "loading",
                    "lease_owner": owner,
                    "lease_expires_at": now
                    + timedelta(seconds=self.lease_seconds),
                }
            )
            return self._fetch_and_publish(
                entry,
                owner=owner,
                utc_date=utc_date,
                fetcher=fetcher,
            )

    def get_reference(
        self, *, user_id, instrument: str, utc_date: date
    ) -> dict:
        """Return cache metadata for a ready day without reading candle bytes."""
        user_oid = user_id if isinstance(user_id, ObjectId) else ObjectId(str(user_id))
        normalized_instrument = str(instrument).strip().upper()
        cache_key = (
            f"{CANDLE_CACHE_VERSION}:{normalized_instrument}:"
            f"{utc_date.isoformat()}"
        )
        entry = self.collection.find_one(
            {"user_id": user_oid, "cache_key": cache_key, "state": "ready"}
        )
        if entry is None:
            raise CachedCandleObjectMissing(cache_key)
        return {
            "cache_key": entry["cache_key"],
            "cache_version": entry.get("cache_version", CANDLE_CACHE_VERSION),
            "instrument": entry.get("instrument", normalized_instrument),
            "utc_date": str(entry.get("utc_date", utc_date.isoformat())),
            "object_key": entry.get("object_key"),
            "sha256": entry.get("sha256"),
            "object_size": entry.get("object_size"),
            "outcome": entry.get("outcome"),
            "candle_count": int(entry.get("candle_count", -1)),
        }

    def references_for_run(self, snapshot: dict) -> list[dict]:
        """Collect unique source and conversion cache refs from run metadata."""
        refs: dict[tuple[str, str], dict] = {}
        for day_index in snapshot.get("_day_candle_indexes", []):
            ref = day_index.get("cache_ref")
            if isinstance(ref, dict):
                item = dict(ref)
                item["kind"] = "replay"
                refs[(str(ref.get("instrument", "")).upper(), str(ref.get("utc_date", "")))] = item
        for series in snapshot.get("fx_conversion_series", []):
            for ref in series.get("_cache_date_refs", []):
                if isinstance(ref, dict):
                    key = (str(ref.get("instrument", "")).upper(), str(ref.get("utc_date", "")))
                    item = dict(ref)
                    item["kind"] = "conversion"
                    # If one instrument/date serves both roles, its replay
                    # normalization is also suitable for the conversion path.
                    refs.setdefault(key, item)
        return list(refs.values())

    def missing_references(self, snapshot: dict) -> list[dict]:
        """Return cache refs whose object is absent or fails integrity checks."""
        # Replay reads are memoized per worker process. A status sweep must
        # bypass that process-local cache so deleted or damaged MinIO objects
        # are detected when a run is reopened.
        self.snapshot_store.clear_cached_candle_reads()
        missing = []
        for ref in self.references_for_run(snapshot):
            if not self.snapshot_store.cached_candle_ref_exists(ref):
                missing.append({
                    "instrument": ref.get("instrument"),
                    "utc_date": ref.get("utc_date"),
                    "kind": ref.get("kind", "replay"),
                })
        return missing

    def _fetch_and_publish(self, entry, *, owner, utc_date, fetcher) -> dict:
        identity = {
            "user_id": entry["user_id"],
            "cache_key": entry["cache_key"],
        }
        lease = _CacheLeaseHeartbeat(
            identity=identity,
            owner=owner,
            lease_seconds=self.lease_seconds,
            clock=self.clock,
        )
        lease.start()
        try:
            result = fetcher()
            if not isinstance(result, dict) or not isinstance(
                result.get("candles"), list
            ):
                raise ValueError("Candle cache fetcher returned an invalid day.")
            if result.get("utc_date") != utc_date:
                raise ValueError("Candle cache fetcher returned an unexpected date.")
            outcome = "data" if result["candles"] else "empty"
            if result.get("outcome") != outcome:
                raise ValueError("Candle cache outcome disagrees with its data.")
            lease.check()
            object_key, checksum, object_size = self.snapshot_store.write_cached_candle_date(
                entry["user_id"],
                entry["instrument"],
                utc_date,
                result["candles"],
                cache_version=CANDLE_CACHE_VERSION,
            )
            lease.check()
            now = _as_utc(self.clock())
            published = self.collection.update_one(
                {
                    **identity,
                    "state": "loading",
                    "lease_owner": owner,
                },
                {
                    "$set": {
                        "state": "ready",
                        "object_key": object_key,
                        "sha256": checksum,
                        "object_size": object_size,
                        "outcome": outcome,
                        "candle_count": len(result["candles"]),
                        "completed_at": now,
                        "updated_at": now,
                    },
                    "$unset": {
                        "lease_owner": "",
                        "lease_expires_at": "",
                        "last_error_type": "",
                    },
                },
            )
            if published.modified_count != 1:
                lease.check()
                # This worker already has a validated copy. Another owner may
                # have replaced the lease while the object was being written;
                # return the copy without recursively acquiring a lease while
                # this heartbeat is still active.
                return result
            return result
        except Exception as exc:
            now = _as_utc(self.clock())
            self.collection.update_one(
                {
                    **identity,
                    "state": "loading",
                    "lease_owner": owner,
                },
                {
                    "$set": {
                        "state": "failed",
                        "last_error_type": type(exc).__name__,
                        "updated_at": now,
                    },
                    "$unset": {
                        "lease_owner": "",
                        "lease_expires_at": "",
                    },
                },
            )
            raise
        finally:
            lease.stop()
