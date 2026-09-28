"""Backend contracts for blind random-period backtest runs."""

from datetime import date, datetime, time, timezone
import re

import pytest
from bson import ObjectId

from app.extensions import mongo


USER_ID = "507f1f77bcf86cd799439011"


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class _FirstChoice:
    def choice(self, candidates):
        assert candidates
        return candidates[0]


class _PriceProvider:
    """Return candles with distinct warm-up and replay reference prices."""

    def __init__(self, prices):
        self.prices = prices

    def fetch_day(self, instrument, utc_date):
        price = self.prices.get(utc_date)
        candles = []
        if price is not None:
            timestamp = int(
                datetime.combine(
                    utc_date, time.min, tzinfo=timezone.utc
                ).timestamp()
                * 1000
            )
            candles.append(
                {
                    "time_ms": timestamp,
                    "open": price,
                    "high": price + 0.5,
                    "low": price - 0.5,
                    "close": price + 0.25,
                    "volume": 1,
                }
            )
        return {
            "utc_date": utc_date,
            "outcome": "data" if candles else "empty",
            "candles": candles,
        }


def _patch_catalog(monkeypatch):
    import app.backtests.service as service_module

    monkeypatch.setattr(
        service_module, "fetch_instrument_codes", lambda: ["EUR-USD"]
    )


def _register(client, username):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "TestPass123!", "timezone": "UTC"},
    )
    assert response.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "TestPass123!"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json['token']}"}


def _create_blind_random_run(app, monkeypatch):
    import app.backtests.service as service_module

    _patch_catalog(monkeypatch)
    with app.app_context():
        return service_module.BacktestService(
            clock=_Clock(datetime(2005, 3, 1, tzinfo=timezone.utc))
        ).create_run(
            user_id=USER_ID,
            instrument="EUR-USD",
            start_date=None,
            end_date=None,
            display_timezone="UTC",
            period_selection="random",
            period_months=1,
            blind_mode=True,
        )


def _restrict_selection_to_january_tenth(run_id):
    job = mongo.db.backtest_preparation_jobs.find_one({"run_id": run_id})
    selection = job["selection"]
    selection.update(
        {
            "minimum_start_date": "2005-01-10",
            "maximum_start_date": "2005-01-10",
            "years_remaining": [2005],
            "current_year": None,
            "tried_dates": [],
            "pending_date": None,
        }
    )
    mongo.db.backtest_preparation_jobs.update_one(
        {"_id": job["_id"]}, {"$set": {"selection": selection}}
    )


def test_legacy_run_defaults_blind_mode_to_false(app, client, monkeypatch):
    _patch_catalog(monkeypatch)
    headers = _register(client, "blind-legacy-default")

    response = client.post(
        "/api/backtest/runs",
        json={
            "instrument": "EUR-USD",
            "start_date": "2026-01-05",
            "end_date": "2026-01-05",
            "display_timezone": "UTC",
        },
        headers=headers,
    )

    assert response.status_code == 202
    run = response.json["run"]
    assert run["blind_mode"] is False

    explicit_false = client.post(
        "/api/backtest/runs",
        json={
            "instrument": "EUR-USD",
            "start_date": "2026-01-06",
            "end_date": "2026-01-06",
            "display_timezone": "UTC",
            "blind_mode": False,
        },
        headers=headers,
    )
    assert explicit_false.status_code == 202
    assert explicit_false.json["run"]["blind_mode"] is False
    with app.app_context():
        stored_runs = list(mongo.db.backtest_runs.find({}))
    assert len(stored_runs) == 2
    assert all(stored["blind_mode"] is False for stored in stored_runs)


def test_blind_mode_requires_random_selection_without_creating_records(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    headers = _register(client, "blind-requires-random")

    response = client.post(
        "/api/backtest/runs",
        json={
            "instrument": "EUR-USD",
            "start_date": "2026-01-05",
            "end_date": "2026-01-05",
            "display_timezone": "UTC",
            "blind_mode": True,
        },
        headers=headers,
    )

    assert response.status_code == 400
    with app.app_context():
        assert mongo.db.backtest_runs.count_documents({}) == 0
        assert mongo.db.trade_accounts.count_documents({}) == 0
        assert mongo.db.backtest_preparation_jobs.count_documents({}) == 0


def test_blind_random_run_creates_date_free_account_and_persists_first_replay_open(
    app, client, monkeypatch
):
    from app.backtests.worker import BacktestWorker

    _patch_catalog(monkeypatch)
    headers = _register(client, "blind-reference-persistence")
    response = client.post(
        "/api/backtest/runs",
        json={
            "instrument": "EUR-USD",
            "display_timezone": "UTC",
            "period_selection": "random",
            "period_months": 1,
            "blind_mode": True,
        },
        headers=headers,
    )
    assert response.status_code == 202
    pending = response.json["run"]
    assert pending["blind_mode"] is True
    assert pending["status"] == "selecting_period"

    run_id = ObjectId(pending["id"])
    with app.app_context():
        _restrict_selection_to_january_tenth(run_id)
        worker = BacktestWorker(
            provider=_PriceProvider(
                {
                    date(2004, 12, 10): 9.0,
                    date(2005, 1, 10): 2.5,
                }
            ),
            clock=_Clock(datetime(2005, 3, 1, tzinfo=timezone.utc)),
            random_source=_FirstChoice(),
            worker_id="blind-reference-worker",
        )
        worker.process_one()
        ready = mongo.db.backtest_runs.find_one({"_id": run_id})
        account = mongo.db.trade_accounts.find_one({"backtest_run_id": run_id})

    assert ready["status"] == "ready"
    assert ready["blind_mode"] is True
    assert ready["normalized_reference_price"] == 2.5
    assert ready["snapshot"]["replay_period_candle_count"] == 1
    assert account is not None
    for label in (account["account_name"], account["display_name"]):
        assert "EUR-USD" in label
        assert "blind" in label.casefold()
        assert re.search(r"\d{4}-\d{2}-\d{2}", label) is None


def test_serialized_blind_run_replaces_legacy_date_bearing_account_label():
    from app.backtests.schemas import serialize_run

    run_id = ObjectId("65a000000000000000000001")
    result = serialize_run(
        {
            "_id": run_id,
            "instrument": "EUR-USD",
            "blind_mode": True,
        },
        {
            "display_name": "Backtest EUR-USD 2026-01-05 to 2026-01-06 (legacy)",
            "account_name": "Backtest EUR-USD 2026-01-05 to 2026-01-06 (legacy)",
        },
    )

    assert result["account_label"] == f"Backtest EUR-USD blind ({run_id})"
    assert "2026-01-05" not in result["account_label"]
    assert "legacy" not in result["account_label"]


def test_ready_legacy_blind_run_backfills_reference_from_first_replay_candle(
    app,
):
    import pandas as pd

    from app.backtests.service import BacktestService

    run_id = ObjectId("65a000000000000000000002")
    with app.app_context():
        mongo.db.backtest_runs.insert_one(
            {
                "_id": run_id,
                "user_id": ObjectId(USER_ID),
                "instrument": "EUR-USD",
                "blind_mode": True,
                "status": "ready",
                "start_utc_ms": 1_000,
                "account_id": None,
                "snapshot": {"object_key": "legacy-snapshot.parquet"},
            }
        )

        class _SnapshotReader:
            def read_snapshot(self, object_key):
                assert object_key == "legacy-snapshot.parquet"
                return pd.DataFrame([
                    {"time_ms": 500, "open": 9.0},
                    {"time_ms": 1_000, "open": 2.5},
                    {"time_ms": 2_000, "open": 3.0},
                ])

        result = BacktestService(
            snapshot_store=_SnapshotReader()
        ).get_run(USER_ID, str(run_id))
        stored = mongo.db.backtest_runs.find_one({"_id": run_id})

    assert result["normalized_reference_price"] == 2.5
    assert stored["normalized_reference_price"] == 2.5


@pytest.mark.parametrize("reference_price", [0.0, float("nan"), float("inf")])
def test_invalid_blind_reference_fails_without_ready_run_or_account(
    app, monkeypatch, reference_price
):
    from app.backtests.worker import BacktestWorker

    run = _create_blind_random_run(app, monkeypatch)
    run_id = ObjectId(run["id"])
    with app.app_context():
        _restrict_selection_to_january_tenth(run_id)
        BacktestWorker(
            provider=_PriceProvider({date(2005, 1, 10): reference_price}),
            clock=_Clock(datetime(2005, 3, 1, tzinfo=timezone.utc)),
            random_source=_FirstChoice(),
            worker_id="blind-invalid-reference-worker",
        ).process_one()

        assert mongo.db.backtest_runs.find_one({"_id": run_id}) is None
        assert mongo.db.trade_accounts.count_documents(
            {"backtest_run_id": run_id}
        ) == 0
        notice = mongo.db.backtest_notices.find_one({"run_id": run_id})

    assert notice is not None
    assert notice["outcome"] == "failed"
    assert notice["dismissed"] is False
    assert "zero or non-finite" in notice["message"].casefold()
    assert "opening price" in notice["message"].casefold()
