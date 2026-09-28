"""Random replay-period selection and recovery contract tests."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from app.extensions import mongo
from app.utils.errors import ValidationError


USER_ID = "507f1f77bcf86cd799439011"


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class _FirstChoice:
    """Deterministic chooser that picks the first remaining candidate."""

    def choice(self, candidates):
        assert candidates
        return candidates[0]


class _ProbeProvider:
    def __init__(self, *, data_dates=(), fail_dates=(), crash_on_call=None):
        self.data_dates = set(data_dates)
        self.fail_dates = set(fail_dates)
        self.crash_on_call = crash_on_call
        self.calls = []

    def fetch_day(self, instrument, utc_date):
        self.calls.append((instrument, utc_date))
        if self.crash_on_call == len(self.calls):
            raise SystemExit("simulated worker termination")
        if utc_date in self.fail_dates:
            raise RuntimeError("provider unavailable")
        if utc_date not in self.data_dates:
            return {"utc_date": utc_date, "outcome": "empty", "candles": []}
        timestamp = int(
            datetime.combine(utc_date, time.min, tzinfo=timezone.utc).timestamp()
            * 1000
        )
        return {
            "utc_date": utc_date,
            "outcome": "data",
            "candles": [
                {
                    "time_ms": timestamp,
                    "open": 1.1,
                    "high": 1.2,
                    "low": 1.0,
                    "close": 1.15,
                    "volume": 1,
                }
            ],
        }


def _create_random_run(app, monkeypatch, *, now, months=1, timezone_name="UTC"):
    import app.backtests.service as service_module

    monkeypatch.setattr(
        service_module, "fetch_instrument_codes", lambda: ["EUR-USD"]
    )
    with app.app_context():
        return service_module.BacktestService(clock=_Clock(now)).create_run(
            user_id=USER_ID,
            instrument="EUR-USD",
            start_date=None,
            end_date=None,
            display_timezone=timezone_name,
            period_selection="random",
            period_months=months,
        )


def _narrow_search(run_id, *, years, minimum, maximum, current_year=None, tried_dates=()):
    job = mongo.db.backtest_preparation_jobs.find_one({"run_id": run_id})
    selection = job["selection"]
    selection.update(
        {
            "minimum_start_date": minimum.isoformat(),
            "maximum_start_date": maximum.isoformat(),
            "years_remaining": list(years),
            "current_year": current_year,
            "tried_dates": [day.isoformat() for day in tried_dates],
            "pending_date": None,
        }
    )
    mongo.db.backtest_preparation_jobs.update_one(
        {"_id": job["_id"]}, {"$set": {"selection": selection}}
    )


def test_random_run_captures_timezone_yesterday_and_creates_no_account(
    app, monkeypatch
):
    run = _create_random_run(
        app,
        monkeypatch,
        now=datetime(2026, 9, 28, 0, 30, tzinfo=timezone.utc),
        months=3,
        timezone_name="Europe/Rome",
    )

    with app.app_context():
        stored = mongo.db.backtest_runs.find_one({"_id": run["id"]})
        job = mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": run["id"]}
        )

        assert stored["status"] == "selecting_period"
        assert stored["requested_start_date"] is None
        assert stored["requested_end_date"] is None
        assert stored["account_id"] is None
        assert stored["period_selection"] == "random"
        assert stored["period_months"] == 3
        assert run["status"] == "selecting_period"
        assert run["requested_start_date"] is None
        assert run["account_id"] is None
        assert job["selection"]["as_of_date"] == "2026-09-27"
        assert job["selection"]["maximum_start_date"] == "2026-06-28"
        assert mongo.db.trade_accounts.count_documents(
            {"backtest_run_id": run["id"]}
        ) == 0


@pytest.mark.parametrize(
    ("start", "months", "expected_end"),
    [
        (date(2023, 1, 31), 1, date(2023, 2, 27)),
        (date(2024, 1, 31), 1, date(2024, 2, 28)),
        (date(2024, 1, 31), 3, date(2024, 4, 29)),
        (date(2024, 2, 29), 12, date(2025, 2, 27)),
    ],
)
def test_calendar_period_end_clamps_month_then_excludes_boundary(
    start, months, expected_end
):
    from app.backtests.service import _random_period_end

    assert _random_period_end(start, months) == expected_end


@pytest.mark.parametrize("months", [1, 3, 6, 12])
def test_latest_random_start_never_ends_after_fixed_cutoff(months):
    from app.backtests.service import _latest_random_start

    cutoff = date(2026, 9, 27)
    latest = _latest_random_start(cutoff, months)

    assert _random_end(latest, months) <= cutoff
    assert _random_end(latest + timedelta(days=1), months) > cutoff


def _random_end(start, months):
    from app.backtests.service import _random_period_end

    return _random_period_end(start, months)


def test_random_request_rejects_unsupported_duration_without_side_effects(
    app, monkeypatch
):
    import app.backtests.service as service_module

    monkeypatch.setattr(
        service_module, "fetch_instrument_codes", lambda: ["EUR-USD"]
    )
    with app.app_context(), pytest.raises(ValidationError):
        service_module.BacktestService().create_run(
            user_id=USER_ID,
            instrument="EUR-USD",
            start_date=None,
            end_date=None,
            display_timezone="UTC",
            period_selection="random",
            period_months=2,
        )

    assert mongo.db.backtest_runs.count_documents({}) == 0
    assert mongo.db.backtest_preparation_jobs.count_documents({}) == 0
    assert mongo.db.trade_accounts.count_documents({}) == 0


def test_worker_tries_ten_dates_per_year_without_replacement_then_continues(
    app, monkeypatch
):
    from app.backtests.worker import BacktestWorker

    run = _create_random_run(
        app,
        monkeypatch,
        now=datetime(2007, 2, 1, tzinfo=timezone.utc),
    )
    with app.app_context():
        _narrow_search(
            run["id"],
            years=[2005, 2006],
            minimum=date(2005, 1, 1),
            maximum=date(2006, 1, 31),
        )
        provider = _ProbeProvider(data_dates={date(2006, 1, 1)})
        BacktestWorker(
            provider=provider,
            clock=_Clock(datetime(2007, 2, 1, tzinfo=timezone.utc)),
            random_source=_FirstChoice(),
            worker_id="year-sampling-worker",
        ).process_one()

        resolved = mongo.db.backtest_runs.find_one({"_id": run["id"]})

    probed = [day for _, day in provider.calls[:11]]
    assert probed[:10] == [date(2005, 1, day) for day in range(1, 11)]
    assert len(set(probed[:10])) == 10
    assert probed[10] == date(2006, 1, 1)
    assert resolved["status"] == "ready"
    assert resolved["requested_start_date"] == "2006-01-01"
    account = mongo.db.trade_accounts.find_one(
        {"backtest_run_id": run["id"]}
    )
    assert account["display_name"].startswith(
        "Backtest EUR-USD 2006-01-01 to 2006-01-31"
    )
    assert resolved["coverage"]["candle_count"] == 1
    assert resolved["warmup_coverage"]["candle_count"] == 0


def test_exhausting_all_years_creates_dismissible_duration_notice_without_account(
    app, monkeypatch
):
    from app.backtests.worker import BacktestWorker

    run = _create_random_run(
        app,
        monkeypatch,
        now=datetime(2007, 2, 1, tzinfo=timezone.utc),
        months=3,
    )
    with app.app_context():
        _narrow_search(
            run["id"],
            years=[2005, 2006],
            minimum=date(2005, 1, 1),
            maximum=date(2006, 1, 31),
        )
        provider = _ProbeProvider()
        BacktestWorker(
            provider=provider,
            clock=_Clock(datetime(2007, 2, 1, tzinfo=timezone.utc)),
            random_source=_FirstChoice(),
            worker_id="exhausted-worker",
        ).process_one()

        notice = mongo.db.backtest_notices.find_one({"run_id": run["id"]})

        assert mongo.db.backtest_runs.find_one({"_id": run["id"]}) is None
        assert mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": run["id"]}
        ) is None
        assert mongo.db.trade_accounts.count_documents(
            {"backtest_run_id": run["id"]}
        ) == 0

    assert len(provider.calls) == 20
    assert len({day for _, day in provider.calls}) == 20
    assert notice["instrument"] == "EUR-USD"
    assert notice["period_months"] == 3
    assert notice["requested_start_date"] is None
    assert notice["requested_end_date"] is None
    assert notice["dismissed"] is False
    assert notice["next_action"] == "start_new_run"
    assert "3-month" in notice["message"]


def test_pending_probe_recovers_after_worker_restart_without_repeating_prior_days(
    app, monkeypatch
):
    from app.backtests.worker import BacktestWorker

    clock = _Clock(datetime(2005, 2, 28, tzinfo=timezone.utc))
    run = _create_random_run(app, monkeypatch, now=clock.now)
    with app.app_context():
        _narrow_search(
            run["id"],
            years=[2005],
            minimum=date(2005, 1, 1),
            maximum=date(2005, 1, 31),
        )
        with pytest.raises(SystemExit, match="simulated worker termination"):
            BacktestWorker(
                provider=_ProbeProvider(crash_on_call=2),
                clock=clock,
                random_source=_FirstChoice(),
                worker_id="interrupted-worker",
                lease_seconds=60,
            ).process_one()

        job = mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": run["id"]}
        )
        assert job["selection"]["tried_dates"] == ["2005-01-01"]
        assert job["selection"]["pending_date"] == "2005-01-02"

        clock.advance(61)
        provider = _ProbeProvider(data_dates={date(2005, 1, 2)})
        BacktestWorker(
            provider=provider,
            clock=clock,
            random_source=_FirstChoice(),
            worker_id="replacement-worker",
            lease_seconds=60,
        ).process_one()

        ready = mongo.db.backtest_runs.find_one({"_id": run["id"]})

    assert provider.calls[0][1] == date(2005, 1, 2)
    assert ready["status"] == "ready"
    assert ready["requested_start_date"] == "2005-01-02"
    accounts = list(mongo.db.trade_accounts.find({"backtest_run_id": run["id"]}))
    assert len(accounts) == 1


def test_provider_error_is_failure_not_an_empty_candidate(app, monkeypatch):
    from app.backtests.worker import BacktestWorker

    run = _create_random_run(
        app,
        monkeypatch,
        now=datetime(2006, 7, 1, tzinfo=timezone.utc),
        months=6,
    )
    with app.app_context():
        _narrow_search(
            run["id"],
            years=[2006],
            minimum=date(2006, 1, 1),
            maximum=date(2006, 1, 1),
        )
        BacktestWorker(
            provider=_ProbeProvider(fail_dates={date(2006, 1, 1)}),
            clock=_Clock(datetime(2006, 7, 1, tzinfo=timezone.utc)),
            random_source=_FirstChoice(),
            worker_id="provider-error-worker",
        ).process_one()

        notice = mongo.db.backtest_notices.find_one({"run_id": run["id"]})

    assert notice["outcome"] == "failed"
    assert notice["period_months"] == 6
    assert notice["error_type"] == "RuntimeError"


def test_delete_during_selection_fences_worker_and_never_creates_account(
    app, monkeypatch
):
    from app.backtests.service import BacktestService
    from app.backtests.worker import BacktestWorker

    run = _create_random_run(
        app,
        monkeypatch,
        now=datetime(2026, 9, 28, tzinfo=timezone.utc),
    )
    with app.app_context():
        assert BacktestService().delete_run(USER_ID, run["id"])["status"] == "deleting"
        provider = _ProbeProvider()
        BacktestWorker(provider=provider, worker_id="delete-selection-worker").process_one()

        assert mongo.db.backtest_runs.find_one({"_id": run["id"]}) is None
        assert mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": run["id"]}
        ) is None
        assert mongo.db.trade_accounts.count_documents(
            {"backtest_run_id": run["id"]}
        ) == 0

    assert provider.calls == []


def test_deletion_during_candle_probe_fences_selection_before_account_creation(
    app, monkeypatch
):
    from app.backtests.service import BacktestService
    from app.backtests.worker import BacktestWorker

    run = _create_random_run(
        app,
        monkeypatch,
        now=datetime(2026, 9, 28, tzinfo=timezone.utc),
    )

    class DeletingProvider(_ProbeProvider):
        def fetch_day(self, instrument, utc_date):
            BacktestService().delete_run(USER_ID, run["id"])
            self.calls.append((instrument, utc_date))
            return {
                "utc_date": utc_date,
                "outcome": "data",
                "candles": [{
                    "time_ms": int(datetime.combine(
                        utc_date, time.min, tzinfo=timezone.utc
                    ).timestamp() * 1000),
                    "open": 1.1,
                    "high": 1.2,
                    "low": 1.0,
                    "close": 1.15,
                }],
            }

    with app.app_context():
        _narrow_search(
            run["id"],
            years=[2026],
            minimum=date(2026, 1, 1),
            maximum=date(2026, 8, 28),
        )
        provider = DeletingProvider()
        worker = BacktestWorker(
            provider=provider,
            random_source=_FirstChoice(),
            worker_id="delete-during-probe-worker",
        )
        worker.process_one()

        pending = mongo.db.backtest_runs.find_one({"_id": run["id"]})
        assert pending["status"] == "deleting"
        assert mongo.db.trade_accounts.count_documents(
            {"backtest_run_id": run["id"]}
        ) == 0

        worker.process_one()
        assert mongo.db.backtest_runs.find_one({"_id": run["id"]}) is None
        assert mongo.db.trade_accounts.count_documents(
            {"backtest_run_id": run["id"]}
        ) == 0


@pytest.mark.parametrize(
    ("local_day", "expected_hours"),
    [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)],
)
def test_local_day_probe_uses_dst_adjusted_display_timezone_bounds(
    local_day, expected_hours
):
    from app.backtests.worker import BacktestWorker

    worker = BacktestWorker(provider=_ProbeProvider())
    timezone_info = ZoneInfo("Europe/Rome")
    start = datetime.combine(local_day, time.min).replace(tzinfo=timezone_info)
    end = datetime.combine(local_day + timedelta(days=1), time.min).replace(
        tzinfo=timezone_info
    )

    bounds = worker._local_day_utc_bounds(local_day, timezone_info)

    assert bounds == (
        int(start.astimezone(timezone.utc).timestamp() * 1000),
        int(end.astimezone(timezone.utc).timestamp() * 1000),
    )
    assert bounds[1] - bounds[0] == expected_hours * 60 * 60 * 1000


def test_local_day_probe_excludes_candles_outside_dst_adjusted_day():
    from app.backtests.worker import BacktestWorker

    local_day = date(2026, 3, 29)
    timezone_info = ZoneInfo("Europe/Rome")
    start = datetime.combine(local_day, time.min).replace(tzinfo=timezone_info)
    end = datetime.combine(local_day + timedelta(days=1), time.min).replace(
        tzinfo=timezone_info
    )
    start_ms = int(start.astimezone(timezone.utc).timestamp() * 1000)
    end_ms = int(end.astimezone(timezone.utc).timestamp() * 1000)

    class BoundaryProvider:
        calls = []

        def fetch_day(self, instrument, utc_date):
            self.calls.append(utc_date)
            timestamp = end_ms if utc_date == date(2026, 3, 29) else start_ms - 1
            return {
                "utc_date": utc_date,
                "outcome": "data",
                "candles": [{"time_ms": timestamp}],
            }

    provider = BoundaryProvider()
    worker = BacktestWorker(provider=provider)
    worker._renew_or_lose = lambda *args: None

    has_candles = worker._probe_local_date(
        "EUR-USD",
        local_day,
        timezone_info,
        {},
        {},
        type("Heartbeat", (), {"check": lambda self: None})(),
    )

    assert has_candles is False
    assert provider.calls == [date(2026, 3, 28), date(2026, 3, 29)]
