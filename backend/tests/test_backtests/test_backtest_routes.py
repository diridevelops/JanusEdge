"""Backtest run and preparation lifecycle route tests."""

from datetime import date, datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.extensions import mongo


def _patch_catalog(monkeypatch):
    import app.backtests.service as service_module

    monkeypatch.setattr(
        service_module,
        "fetch_instrument_codes",
        lambda: ["EUR-USD", "GBP-USD"],
    )


def _register(client, username):
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "TestPass123!",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "TestPass123!"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json['token']}"}


def _create_run(
    client, headers, *, start="2026-01-05", end="2026-01-05", warmup_days=0
):
    response = client.post(
        "/api/backtest/runs",
        json={
            "instrument": "EUR-USD",
            "start_date": start,
            "end_date": end,
            "display_timezone": "UTC",
            "warmup_days": warmup_days,
        },
        headers=headers,
    )
    assert response.status_code == 202
    return response.json["run"]


class _Clock:
    """A controllable UTC clock for lease recovery tests."""

    def __init__(self):
        self.now = datetime(2026, 12, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, delta):
        self.now += delta


class _FakeProvider:
    """Return configured per-UTC-date outcomes without network access."""

    def __init__(self, outcomes, on_fetch=None):
        self.outcomes = outcomes
        self.on_fetch = on_fetch
        self.calls = []

    def fetch_day(self, instrument, utc_date):
        self.calls.append(utc_date)
        if self.on_fetch is not None:
            self.on_fetch(instrument, utc_date)
        outcome = self.outcomes.get(utc_date, _day_result(utc_date, []))
        if callable(outcome):
            outcome = outcome()
        return outcome


class _WorkerStopped(BaseException):
    """Simulate process death, which must leave the job recoverable."""


def _candle(utc_date, minute=0, price=1.1):
    timestamp = int(
        datetime(
            utc_date.year,
            utc_date.month,
            utc_date.day,
            tzinfo=timezone.utc,
        ).timestamp()
        * 1000
    ) + minute * 60_000
    return {
        "time_ms": timestamp,
        "open": price,
        "high": price + 0.001,
        "low": price - 0.001,
        "close": price + 0.0005,
        "volume": 30,
    }


def _day_result(utc_date, candles):
    return {
        "utc_date": utc_date,
        "outcome": "data" if candles else "empty",
        "candles": candles,
    }


def _stored_date(value):
    return value.date() if isinstance(value, datetime) else value


def _stored_datetime_as_utc(value):
    """Treat BSON datetimes returned without tzinfo as UTC instants."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def test_run_list_reads_persisted_progress_and_retry_is_idempotent(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    headers = _register(client, "backtest-progress")
    run = _create_run(client, headers)
    run_id = ObjectId(run["id"])

    with app.app_context():
        mongo.db.backtest_runs.update_one(
            {"_id": run_id},
            {"$set": {"progress": {"stage": "downloading", "percent": 50}}},
        )

    listed = client.get("/api/backtest/runs", headers=headers)
    assert listed.status_code == 200
    listed_run = next(item for item in listed.json["runs"] if item["id"] == run["id"])
    assert listed_run["progress"] == {
        "stage": "downloading",
        "percent": 50,
    }

    first_retry = client.post(
        f"/api/backtest/runs/{run['id']}/retry", headers=headers
    )
    second_retry = client.post(
        f"/api/backtest/runs/{run['id']}/retry", headers=headers
    )
    assert first_retry.status_code == 202
    assert second_retry.status_code == 202
    assert first_retry.json["run"]["id"] == run["id"]
    assert second_retry.json["run"]["id"] == run["id"]

    with app.app_context():
        assert mongo.db.backtest_runs.count_documents({"_id": run_id}) == 1
        assert mongo.db.trade_accounts.count_documents(
            {"backtest_run_id": run_id}
        ) == 1
        assert mongo.db.backtest_preparation_jobs.count_documents(
            {"run_id": run_id}
        ) == 1


def test_random_run_request_returns_pending_selection_without_dates_or_account(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    headers = _register(client, "backtest-random-period-api")

    response = client.post(
        "/api/backtest/runs",
        json={
            "instrument": "EUR-USD",
            "display_timezone": "Europe/Rome",
            "period_selection": "random",
            "period_months": 3,
        },
        headers=headers,
    )

    assert response.status_code == 202
    run = response.json["run"]
    assert run["status"] == "selecting_period"
    assert run["period_selection"] == "random"
    assert run["period_months"] == 3
    assert run["requested_start_date"] is None
    assert run["requested_end_date"] is None
    assert run["account_id"] is None

    listed = client.get("/api/backtest/runs", headers=headers)
    listed_run = next(
        item for item in listed.json["runs"] if item["id"] == run["id"]
    )
    assert listed_run["status"] == "selecting_period"
    assert listed_run["requested_start_date"] is None
    assert listed_run["account_id"] is None

def test_worker_reports_partial_and_empty_dates_and_keeps_ready_snapshot_immutable(
    app, client, monkeypatch
):
    from app.backtests.worker import BacktestWorker

    _patch_catalog(monkeypatch)
    headers = _register(client, "backtest-gaps")
    run = _create_run(
        client,
        headers,
        start="2026-01-05",
        end="2026-01-06",
        warmup_days=31,
    )
    run_object_id = ObjectId(run["id"])
    clock = _Clock()
    observed_progress = []

    def observe_progress(instrument, utc_date):
        with app.app_context():
            current = mongo.db.backtest_runs.find_one(
                {"_id": run_object_id}
            )
        observed_progress.append(current["progress"])

    warmup_date = date(2025, 12, 5)
    provider = _FakeProvider(
        {
            warmup_date: _day_result(
                warmup_date, [_candle(warmup_date, price=0.9)]
            ),
            date(2026, 1, 5): _day_result(
                date(2026, 1, 5),
                [_candle(date(2026, 1, 5)), _candle(date(2026, 1, 5), 2)],
            ),
            date(2026, 1, 6): _day_result(date(2026, 1, 6), []),
        },
        on_fetch=observe_progress,
    )
    worker = BacktestWorker(provider=provider, clock=clock)
    with app.app_context():
        worker.process_one()
        ready = mongo.db.backtest_runs.find_one({"_id": run_object_id})

    assert ready["status"] == "ready"
    assert observed_progress
    assert all("stage" in progress and "percent" in progress for progress in observed_progress)
    assert all(
        progress["percent"] is None
        or 0 <= progress["percent"] <= 100
        for progress in observed_progress
    )
    snapshot = ready["snapshot"]
    assert snapshot["candle_count"] == 3
    assert snapshot["replay_period_candle_count"] == 2
    assert snapshot["replay_start_source_index"] == 1
    assert ready["warmup_coverage"]["candle_count"] == 1
    assert snapshot["source_side"] == "COMB"
    assert snapshot["price_mode"] == "combined_midpoint"
    assert snapshot["volume_semantics"] == "two_sided_quote_liquidity"
    assert date(2026, 1, 6) in {
        _stored_date(value) for value in snapshot["gap_dates"]
    }
    assert snapshot["partial_gap_summary"]

    original_snapshot = dict(snapshot)
    refreshed = _FakeProvider(
        {
            date(2026, 1, 5): _day_result(
                date(2026, 1, 5), [_candle(date(2026, 1, 5), price=9.9)]
            ),
            date(2026, 1, 6): _day_result(date(2026, 1, 6), []),
        }
    )
    with app.app_context():
        BacktestWorker(provider=refreshed, clock=clock).process_one()
        after_refresh = mongo.db.backtest_runs.find_one(
            {"_id": run_object_id}
        )

    assert refreshed.calls == []
    assert after_refresh["snapshot"] == original_snapshot


def test_warmup_only_candles_do_not_make_a_run_ready(
    app, client, monkeypatch
):
    from app.backtests.worker import BacktestWorker

    _patch_catalog(monkeypatch)
    headers = _register(client, "backtest-warmup-only")
    run = _create_run(client, headers, warmup_days=31)
    run_id = ObjectId(run["id"])
    warmup_date = date(2025, 12, 5)
    provider = _FakeProvider(
        {warmup_date: _day_result(warmup_date, [_candle(warmup_date)])}
    )

    with app.app_context():
        BacktestWorker(provider=provider, clock=_Clock()).process_one()
        assert mongo.db.backtest_runs.count_documents({"_id": run_id}) == 0

    notices = client.get("/api/backtest/notices", headers=headers)
    assert notices.status_code == 200
    assert notices.json["notices"][0]["outcome"] == "no_data"


@pytest.mark.parametrize(
    ("outcome", "expected_notice", "expected_action"),
    [
        ("empty", "no_data", "edit_range"),
        ("failure", "failed", "start_new_run"),
    ],
)
def test_no_data_and_terminal_failure_remove_run_account_job_but_keep_notice(
    app,
    client,
    monkeypatch,
    outcome,
    expected_notice,
    expected_action,
):
    from app.backtests.worker import BacktestWorker

    _patch_catalog(monkeypatch)
    headers = _register(client, f"backtest-{outcome}")
    run = _create_run(client, headers)
    run_object_id = ObjectId(run["id"])
    utc_date = date(2026, 1, 5)

    def fail_provider_call():
        raise RuntimeError("mock provider failure")

    provider = _FakeProvider(
        {
            utc_date: (
                _day_result(utc_date, [])
                if outcome == "empty"
                else fail_provider_call
            )
        }
    )
    with app.app_context():
        BacktestWorker(provider=provider, clock=_Clock()).process_one()
        assert mongo.db.backtest_runs.count_documents(
            {"_id": run_object_id}
        ) == 0
        assert mongo.db.trade_accounts.count_documents(
            {"backtest_run_id": run_object_id}
        ) == 0
        assert mongo.db.backtest_preparation_jobs.count_documents(
            {"run_id": run_object_id}
        ) == 0

    notice_response = client.get("/api/backtest/notices", headers=headers)
    assert notice_response.status_code == 200
    assert len(notice_response.json["notices"]) == 1
    notice = notice_response.json["notices"][0]
    assert notice["outcome"] == expected_notice
    assert notice["next_action"] == expected_action
    assert notice["instrument"] == "EUR-USD"

    dismissed = client.delete(
        f"/api/backtest/notices/{notice['id']}", headers=headers
    )
    assert dismissed.status_code == 200
    assert client.get(
        "/api/backtest/notices", headers=headers
    ).json["notices"] == []


def test_expired_lease_resumes_after_completed_utc_date_checkpoint(
    app, client, monkeypatch
):
    from app.backtests.worker import BacktestWorker

    _patch_catalog(monkeypatch)
    headers = _register(client, "backtest-recovery")
    run = _create_run(
        client,
        headers,
        start="2026-01-05",
        end="2026-01-07",
        warmup_days=31,
    )
    run_object_id = ObjectId(run["id"])
    first_day, interrupted_day, last_day = (
        date(2025, 12, 5),
        date(2025, 12, 6),
        date(2026, 1, 7),
    )
    replay_day = date(2026, 1, 5)
    calls_for_interrupted_day = 0

    def interrupted_once():
        nonlocal calls_for_interrupted_day
        calls_for_interrupted_day += 1
        if calls_for_interrupted_day == 1:
            raise _WorkerStopped()
        return _day_result(
            interrupted_day,
            [_candle(interrupted_day, price=1.2)],
        )

    provider = _FakeProvider(
        {
            first_day: _day_result(first_day, [_candle(first_day)]),
            interrupted_day: interrupted_once,
            last_day: _day_result(last_day, []),
            replay_day: _day_result(
                replay_day, [_candle(replay_day, price=1.3)]
            ),
        }
    )
    clock = _Clock()
    worker = BacktestWorker(provider=provider, clock=clock)

    with app.app_context(), pytest.raises(_WorkerStopped):
        worker.process_one()

    with app.app_context():
        interrupted_job = mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": run_object_id}
        )
        assert interrupted_job["state"] == "running"
        checkpoint_dates = [
            _stored_date(item["utc_date"])
            for item in interrupted_job["completed_utc_dates"]
        ]
        assert checkpoint_dates == [first_day]
        lease_expires_at = _stored_datetime_as_utc(
            interrupted_job["lease_expires_at"]
        )
        assert lease_expires_at.timestamp() > clock().timestamp()

    clock.advance(timedelta(days=1))
    with app.app_context():
        BacktestWorker(provider=provider, clock=clock).process_one()
        ready = mongo.db.backtest_runs.find_one({"_id": run_object_id})
        completed_job = mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": run_object_id}
        )

    assert provider.calls == [
        first_day,
        interrupted_day,
        interrupted_day,
        *[date(2025, 12, day) for day in range(7, 32)],
        *[date(2026, 1, day) for day in range(1, 8)],
    ]
    assert ready["status"] == "ready"
    assert completed_job["state"] == "completed"
    assert [
        _stored_date(item["utc_date"])
        for item in completed_job["completed_utc_dates"]
    ] == [
        first_day,
        interrupted_day,
        *[date(2025, 12, day) for day in range(7, 32)],
        *[date(2026, 1, day) for day in range(1, 8)],
    ]
    with app.app_context():
        assert mongo.db.trade_accounts.count_documents(
            {"backtest_run_id": run_object_id}
        ) == 1
        assert mongo.db.backtest_runs.count_documents(
            {"_id": run_object_id}
        ) == 1
