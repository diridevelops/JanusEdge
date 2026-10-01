"""Pinned one-minute FX series and causal event-time conversion rates."""

from datetime import date, datetime, timezone

import pytest


def test_conversion_specs_select_direct_inverse_and_identity_sources():
    from app.backtests.fx_conversion import (
        build_conversion_spec,
        quote_currency_from_instrument,
    )

    assert quote_currency_from_instrument("USD-JPY") == "JPY"
    assert build_conversion_spec("EUR")["instrument"] == "EUR-USD"
    assert build_conversion_spec("EUR")["direction"] == "direct"
    assert build_conversion_spec("JPY")["instrument"] == "USD-JPY"
    assert build_conversion_spec("JPY")["direction"] == "inverse"
    assert build_conversion_spec("USD")["direction"] == "identity"
    assert build_conversion_spec("USD")["instrument"] is None


def test_rate_uses_latest_completed_observation_as_of_event():
    from app.backtests.fx_conversion import resolve_quote_to_usd_rate

    observations = [
        {"time_ms": 0, "close": 1.2},
        {"time_ms": 60_000, "close": 1.3},
    ]

    # At 90 seconds the second candle is still open; only the first is complete.
    assert resolve_quote_to_usd_rate("EUR", 90_000, observations) == 1.2
    # At 120 seconds the second candle has completed and becomes eligible.
    assert resolve_quote_to_usd_rate("EUR", 120_000, observations) == 1.3
    assert resolve_quote_to_usd_rate(
        "JPY", 120_000, [{"time_ms": 60_000, "close": 150.0}], direction="inverse"
    ) == pytest.approx(1 / 150.0)
    assert resolve_quote_to_usd_rate("USD", 0, []) == 1.0


def test_missing_eligible_rate_fails_clearly():
    from app.backtests.fx_conversion import (
        FXConversionUnavailable,
        resolve_quote_to_usd_rate,
    )

    with pytest.raises(FXConversionUnavailable, match="quote currency JPY"):
        resolve_quote_to_usd_rate(
            "JPY", 59_999, [{"time_ms": 0, "close": 150.0}], direction="inverse"
        )
    with pytest.raises(FXConversionUnavailable):
        resolve_quote_to_usd_rate(
            "JPY",
            180_000,
            [
                {"time_ms": 0, "close": 0},
                {"time_ms": 60_000, "close": float("nan")},
            ],
            direction="inverse",
        )


def test_preparation_job_pins_conversion_contract():
    from bson import ObjectId

    from app.backtests.preparation_jobs import PreparationJobService

    common = {
        "job_id": ObjectId(),
        "user_id": ObjectId(),
        "run_id": ObjectId(),
        "instrument": "USD-JPY",
        "requested_start_date": date(2026, 1, 5),
        "requested_end_date": date(2026, 1, 5),
        "context_start_utc_date": date(2025, 12, 5),
        "end_utc_date": date(2026, 1, 5),
        "staging_prefix": "backtests/test/staging/",
    }

    job = PreparationJobService().build_for_run(**common)
    assert job["fx_conversion"] == {
        "quote_currency": "JPY",
        "instrument": "USD-JPY",
        "direction": "inverse",
        "supported": True,
        "completed_utc_dates": [],
    }


def test_snapshot_publishes_and_reads_immutable_conversion_series(app):
    from app.backtests.snapshot_store import SnapshotStore

    store = SnapshotStore()
    day = date(1970, 1, 1)
    user_id = "test-user"
    run_id = "test-run"
    base_candles = [
        {"time_ms": 0, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 2},
        {"time_ms": 60_000, "open": 1.5, "high": 2, "low": 1, "close": 1.6, "volume": 2},
    ]
    fx_candles = [
        {"time_ms": 0, "open": 149, "high": 151, "low": 148, "close": 150},
        {"time_ms": 60_000, "open": 150, "high": 152, "low": 149, "close": 151},
    ]

    with app.app_context():
        base_key = store.write_staged_date(user_id, run_id, day, base_candles)
        fx_key = store.write_staged_conversion_date(
            user_id, run_id, "JPY", day, fx_candles
        )
        snapshot, _coverage = store.assemble_snapshot(
            user_id=user_id,
            run={
                "_id": run_id,
                "instrument": "USD-JPY",
                "start_utc_ms": 60_000,
                "context_start_utc_ms": 0,
                "end_utc_ms": 120_000,
            },
            completed_dates=[
                {
                    "utc_date": datetime(1970, 1, 1, tzinfo=timezone.utc),
                    "outcome": "data",
                    "object_key": base_key,
                }
            ],
            fx_conversion={
                "quote_currency": "JPY",
                "instrument": "USD-JPY",
                "direction": "inverse",
                "completed_utc_dates":[
                    {
                        "utc_date": datetime(1970, 1, 1, tzinfo=timezone.utc),
                        "outcome": "data",
                        "object_key": fx_key,
                    }
                ],
            },
        )

        ref = snapshot["fx_conversion_series"][0]
        read_back = store.read_fx_conversion_series(snapshot, "JPY")

    assert ref["instrument"] == "USD-JPY"
    assert ref["direction"] == "inverse"
    assert ref["candle_count"] == 2
    assert ref["source_start_utc_ms"] == 0
    assert ref["source_end_utc_ms"] == 120_000
    assert [row["close"] for row in read_back] == [150.0, 151.0]


def test_worker_checkpoints_and_publishes_inverse_conversion_data(app, monkeypatch):
    from app.backtests.service import BacktestService
    from app.backtests.worker import BacktestWorker
    from app.extensions import mongo

    import app.backtests.service as service_module

    monkeypatch.setattr(
        service_module, "fetch_instrument_codes", lambda: ["USD-JPY"]
    )

    class Provider:
        def __init__(self):
            self.conversion_calls = []

        def fetch_day(self, instrument, utc_date):
            time_ms = int(
                datetime.combine(
                    utc_date, datetime.min.time(), tzinfo=timezone.utc
                ).timestamp()
                * 1000
            )
            return {
                "utc_date": utc_date,
                "outcome": "data",
                "candles": [
                    {
                        "time_ms": time_ms,
                        "open": 150.0,
                        "high": 151.0,
                        "low": 149.0,
                        "close": 150.5,
                        "volume": 10,
                    }
                ],
            }

        def fetch_conversion_day(self, instrument, utc_date):
            self.conversion_calls.append((instrument, utc_date))
            return self.fetch_day(instrument, utc_date)

    with app.app_context():
        run = BacktestService().create_run(
            user_id="507f1f77bcf86cd799439011",
            instrument="USD-JPY",
            start_date="2026-01-05",
            end_date="2026-01-05",
            display_timezone="UTC",
        )
        provider = Provider()
        assert BacktestWorker(
            provider=provider, worker_id="fx-worker", lease_seconds=60
        ).process_one()
        stored_run = mongo.db.backtest_runs.find_one({"_id": run["id"]})
        stored_job = mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": run["id"]}
        )

    ref = stored_run["snapshot"]["fx_conversion_series"][0]
    assert stored_run["status"] == "ready"
    assert ref["quote_currency"] == "JPY"
    assert ref["instrument"] == "USD-JPY"
    assert ref["direction"] == "inverse"
    assert ref["candle_count"] == 32
    assert len(provider.conversion_calls) == 32
    assert all(item[0] == "USD-JPY" for item in provider.conversion_calls)
    assert len(stored_job["fx_conversion"]["completed_utc_dates"]) == 32
