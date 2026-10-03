"""Shared Dukascopy day-cache behavior and lifecycle tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import threading
import time

from bson import ObjectId


def _day(utc_date, candles):
    return {
        "utc_date": utc_date,
        "outcome": "data" if candles else "empty",
        "candles": candles,
    }


def test_cache_reuses_data_and_empty_days_per_user_and_survives_run_cleanup(app):
    from app.backtests.candle_cache import BacktestCandleCache
    from app.backtests.snapshot_store import SnapshotStore

    day = date(2026, 2, 3)
    user_id = ObjectId()
    other_user_id = ObjectId()
    candle = {
        "time_ms": int(
            datetime(2026, 2, 3, tzinfo=timezone.utc).timestamp() * 1000
        ),
        "open": 1.1,
        "high": 1.2,
        "low": 1.0,
        "close": 1.15,
        "volume": 10,
    }
    calls = []

    def fetch_data():
        calls.append("data")
        return _day(day, [candle])

    def fetch_empty():
        calls.append("empty")
        return _day(day, [])

    with app.app_context():
        store = SnapshotStore()
        cache = BacktestCandleCache(snapshot_store=store)
        assert cache.get_or_fetch(
            user_id=user_id,
            instrument="EUR-USD",
            utc_date=day,
            fetcher=fetch_data,
        ) == _day(day, [candle])
        cached = cache.get_or_fetch(
            user_id=user_id,
            instrument="EUR-USD",
            utc_date=day,
            fetcher=lambda: (_ for _ in ()).throw(AssertionError("cache miss")),
        )
        assert cached["candles"] == [candle]

        empty = cache.get_or_fetch(
            user_id=user_id,
            instrument="GBP-USD",
            utc_date=day,
            fetcher=fetch_empty,
        )
        empty_again = cache.get_or_fetch(
            user_id=user_id,
            instrument="GBP-USD",
            utc_date=day,
            fetcher=lambda: (_ for _ in ()).throw(AssertionError("cache miss")),
        )
        assert empty == empty_again == _day(day, [])

        # A run cleanup only removes its own prefix, not the retained user cache.
        store.remove_run_objects(user_id, ObjectId())
        after_run_cleanup = cache.get_or_fetch(
            user_id=user_id,
            instrument="EUR-USD",
            utc_date=day,
            fetcher=lambda: (_ for _ in ()).throw(AssertionError("cache miss")),
        )

        # Another user's cache is isolated and therefore fetches its own day.
        other_user = cache.get_or_fetch(
            user_id=other_user_id,
            instrument="EUR-USD",
            utc_date=day,
            fetcher=fetch_data,
        )

    assert after_run_cleanup["candles"] == [candle]
    assert other_user["candles"] == [candle]
    assert calls == ["data", "empty", "data"]


def test_concurrent_cache_misses_share_one_download(app):
    from app.backtests.candle_cache import BacktestCandleCache

    day = date(2026, 2, 4)
    user_id = ObjectId()
    calls = []
    calls_lock = threading.Lock()

    def fetcher():
        with calls_lock:
            calls.append(1)
        time.sleep(0.15)
        return _day(
            day,
            [
                {
                    "time_ms": int(
                        datetime(2026, 2, 4, tzinfo=timezone.utc).timestamp()
                        * 1000
                    ),
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": 1.0,
                    "volume": 1,
                }
            ],
        )

    cache = BacktestCandleCache(poll_seconds=0.02)

    def read_day():
        with app.app_context():
            return cache.get_or_fetch(
                user_id=user_id,
                instrument="AAPL.US-USD",
                utc_date=day,
                fetcher=fetcher,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: read_day(), range(2)))

    assert len(calls) == 1
    assert first == second


def test_cache_format_version_uses_a_separate_namespace(app, monkeypatch):
    import app.backtests.candle_cache as candle_cache_module
    from app.backtests.candle_cache import BacktestCandleCache

    day = date(2026, 2, 5)
    user_id = ObjectId()
    calls = []

    def fetcher():
        calls.append(1)
        return _day(day, [])

    cache = BacktestCandleCache()
    with app.app_context():
        cache.get_or_fetch(
            user_id=user_id,
            instrument="EUR-USD",
            utc_date=day,
            fetcher=fetcher,
        )
        monkeypatch.setattr(
            candle_cache_module, "CANDLE_CACHE_VERSION", "dukascopy-comb-1m-v2"
        )
        cache.get_or_fetch(
            user_id=user_id,
            instrument="EUR-USD",
            utc_date=day,
            fetcher=fetcher,
        )

    assert len(calls) == 2
