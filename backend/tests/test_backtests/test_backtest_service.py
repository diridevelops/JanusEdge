"""Backtest run validation and account-creation contract tests."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.extensions import mongo
from app.utils.errors import ValidationError


INSTRUMENTS = ["EUR-USD", "GBP-USD"]


@pytest.fixture
def backtest_service(monkeypatch):
    """Use a fixed catalog without reaching Dukascopy or the network."""
    import app.backtests.service as service_module

    monkeypatch.setattr(
        service_module, "fetch_instrument_codes", lambda: INSTRUMENTS
    )
    return service_module.BacktestService()


def _new_run(
    service,
    *,
    instrument="EUR-USD",
    start_date="2026-03-29",
    end_date="2026-03-29",
    display_timezone="Europe/Rome",
    warmup_days=0,
    initial_balance_usd=10_000,
    risk_percent=1.0,
    execution_costs=None,
):
    return service.create_run(
        user_id="507f1f77bcf86cd799439011",
        instrument=instrument,
        start_date=start_date,
        end_date=end_date,
        display_timezone=display_timezone,
        warmup_days=warmup_days,
        initial_balance_usd=initial_balance_usd,
        risk_percent=risk_percent,
        execution_costs=execution_costs,
    )


def test_create_run_validates_instrument_against_current_catalog(
    app, backtest_service
):
    """An instrument outside the current source catalog creates nothing."""
    with app.app_context(), pytest.raises(ValidationError):
        _new_run(backtest_service, instrument="NOT-A-SYMBOL")

    assert mongo.db.backtest_runs.count_documents({}) == 0
    assert mongo.db.trade_accounts.count_documents(
        {"backtest_run_id": {"$exists": True}}
    ) == 0
    assert mongo.db.backtest_preparation_jobs.count_documents({}) == 0


def test_create_run_rejects_unknown_iana_timezone_without_side_effects(
    app, backtest_service
):
    """An invalid display timezone is rejected before run/account/job creation."""
    with app.app_context(), pytest.raises(ValidationError):
        _new_run(
            backtest_service,
            display_timezone="Mars/Olympus",
        )

    assert mongo.db.backtest_runs.count_documents({}) == 0
    assert mongo.db.trade_accounts.count_documents(
        {"backtest_run_id": {"$exists": True}}
    ) == 0
    assert mongo.db.backtest_preparation_jobs.count_documents({}) == 0


def test_create_run_converts_inclusive_display_dates_to_utc_day_bounds(
    app, backtest_service
):
    """Europe/Rome DST start day spans 23 hours in UTC, with an exclusive end."""
    with app.app_context():
        result = _new_run(backtest_service)
        run = mongo.db.backtest_runs.find_one(
            {"_id": result["id"]}
        )

    assert run["requested_start_date"] == "2026-03-29"
    assert run["requested_end_date"] == "2026-03-29"
    assert run["display_timezone"] == "Europe/Rome"
    assert datetime.fromtimestamp(
        run["start_utc_ms"] / 1000, tz=timezone.utc
    ) == datetime(2026, 3, 28, 23, 0, tzinfo=timezone.utc)
    assert datetime.fromtimestamp(
        run["end_utc_ms"] / 1000, tz=timezone.utc
    ) == datetime(2026, 3, 29, 22, 0, tzinfo=timezone.utc)


def test_create_run_persists_default_balance_and_risk_on_run_and_account(
    app, backtest_service
):
    with app.app_context():
        result = _new_run(backtest_service)
        run = mongo.db.backtest_runs.find_one({"_id": result["id"]})
        account = mongo.db.trade_accounts.find_one({"_id": result["account_id"]})

    assert run["initial_balance_usd"] == 10_000
    assert run["current_balance_usd"] == 10_000
    assert run["risk_percent"] == 1.0
    assert account["starting_balance_usd"] == 10_000
    assert account["current_balance_usd"] == 10_000
    assert account["risk_percent"] == 1.0
    assert result["initial_balance_usd"] == 10_000
    assert result["risk_percent"] == 1.0
    metadata = run["instrument_metadata"]
    assert metadata["instrument"] == "EUR-USD"
    assert metadata["instrument_type"] == "forex"
    assert metadata["supported_for_simulation"] is True
    assert metadata["sizing_supported"] is True
    assert metadata["conversion_supported"] is True
    assert metadata["base_currency"] == "EUR"
    assert metadata["quote_currency"] == "USD"
    assert metadata["pip_size"] == 0.0001
    assert metadata["tick_size"] == 0.00001
    assert metadata["price_precision"] == 5
    assert metadata["contract_size"] == 100_000.0
    assert metadata["min_lots"] == 0.01
    assert metadata["lot_increment"] == 0.00001
    assert metadata["pip_value_per_standard_lot"] == 10.0
    assert metadata["conversion_spec"]["supported"] is True
    assert metadata["conversion_spec"]["route"] == []


def test_create_run_persists_custom_balance_and_risk(app, backtest_service):
    with app.app_context():
        result = _new_run(
            backtest_service,
            initial_balance_usd=25_000.5,
            risk_percent=2.5,
        )
        run = mongo.db.backtest_runs.find_one({"_id": result["id"]})
        account = mongo.db.trade_accounts.find_one({"_id": result["account_id"]})

    assert run["initial_balance_usd"] == 25_000.5
    assert run["risk_percent"] == 2.5
    assert account["starting_balance_usd"] == 25_000.5
    assert account["risk_percent"] == 2.5


def test_create_run_persists_custom_execution_costs(app, backtest_service):
    costs = {
        "total_spread_pips": 1.2,
        "slippage_pips": 0.4,
        "commission_usd_per_lot_per_side": 2.5,
    }
    with app.app_context():
        result = _new_run(backtest_service, execution_costs=costs)
        run = mongo.db.backtest_runs.find_one({"_id": result["id"]})

    assert run["execution_costs"] == costs
    assert result["execution_costs"] == costs


@pytest.mark.parametrize(
    "costs",
    [
        {"total_spread_pips": -0.1, "slippage_pips": 0, "commission_usd_per_lot_per_side": 0},
        {"total_spread_pips": True, "slippage_pips": 0, "commission_usd_per_lot_per_side": 0},
        {"total_spread_pips": float("nan"), "slippage_pips": 0, "commission_usd_per_lot_per_side": 0},
    ],
)
def test_create_run_rejects_invalid_execution_costs_without_side_effects(
    app, backtest_service, costs
):
    with app.app_context(), pytest.raises(ValidationError):
        _new_run(backtest_service, execution_costs=costs)

    assert mongo.db.backtest_runs.count_documents({}) == 0
    assert mongo.db.trade_accounts.count_documents(
        {"backtest_run_id": {"$exists": True}}
    ) == 0
    assert mongo.db.backtest_preparation_jobs.count_documents({}) == 0


@pytest.mark.parametrize(
    ("balance", "risk"),
    [
        (0, 1),
        (-1, 1),
        (float("nan"), 1),
        (float("inf"), 1),
        (10_000, 0),
        (10_000, -1),
        (10_000, 100.01),
        (10_000, float("nan")),
        (10_000, float("inf")),
        (True, 1),
    ],
)
def test_create_run_rejects_invalid_balance_or_risk_without_side_effects(
    app, backtest_service, balance, risk
):
    with app.app_context(), pytest.raises(ValidationError):
        _new_run(
            backtest_service,
            initial_balance_usd=balance,
            risk_percent=risk,
        )

    assert mongo.db.backtest_runs.count_documents({}) == 0
    assert mongo.db.trade_accounts.count_documents(
        {"backtest_run_id": {"$exists": True}}
    ) == 0
    assert mongo.db.backtest_preparation_jobs.count_documents({}) == 0


@pytest.mark.parametrize(
    ("start", "warmup_days", "expected_context_date"),
    [
        (date(2026, 3, 31), 31, date(2026, 2, 28)),
        (date(2024, 3, 31), 31, date(2024, 2, 29)),
        (date(2026, 3, 29), 29, date(2026, 2, 28)),
    ],
)
def test_create_run_stores_requested_warmup_day_boundary(
    app, backtest_service, start, warmup_days, expected_context_date
):
    """Warm-up subtracts the requested calendar days before UTC conversion."""
    with app.app_context():
        result = _new_run(
            backtest_service,
            start_date=start.isoformat(),
            end_date=start.isoformat(),
            display_timezone="Europe/Rome",
            warmup_days=warmup_days,
        )
        run = mongo.db.backtest_runs.find_one({"_id": result["id"]})
        job = mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": result["id"]}
        )

    expected_context = datetime(
        expected_context_date.year,
        expected_context_date.month,
        expected_context_date.day,
        tzinfo=ZoneInfo("Europe/Rome"),
    ).astimezone(timezone.utc)
    assert run["requested_start_date"] == start.isoformat()
    assert run["context_start_utc_ms"] == int(expected_context.timestamp() * 1000)
    assert job["next_utc_date"].date() == expected_context.date()


def test_inclusive_one_calendar_year_limit_and_february_29_rule(
    app, backtest_service
):
    """End date may be the day before the anniversary, including leap starts."""
    with app.app_context():
        valid_regular = _new_run(
            backtest_service,
            start_date="2025-04-10",
            end_date="2026-04-09",
            display_timezone="UTC",
        )
        valid_leap = _new_run(
            backtest_service,
            start_date="2024-02-29",
            end_date="2025-02-28",
            display_timezone="UTC",
        )

        assert valid_regular["id"]
        assert valid_leap["id"]

        with pytest.raises(ValidationError):
            _new_run(
                backtest_service,
                start_date="2025-04-10",
                end_date="2026-04-10",
                display_timezone="UTC",
            )
        with pytest.raises(ValidationError):
            _new_run(
                backtest_service,
                start_date="2024-02-29",
                end_date="2025-03-01",
                display_timezone="UTC",
            )


def test_each_run_has_exactly_one_backtest_account(
    app, backtest_service
):
    """Repeatedly creating same-range runs associates one account with each."""
    with app.app_context():
        first = _new_run(backtest_service)
        second = _new_run(backtest_service)

        for run in (first, second):
            accounts = list(
                mongo.db.trade_accounts.find(
                    {"backtest_run_id": run["id"]}
                )
            )
            assert len(accounts) == 1
            assert accounts[0]["_id"] == run["account_id"]

        account_labels = {
            account["display_name"]
            for account in mongo.db.trade_accounts.find(
                {"backtest_run_id": {"$in": [first["id"], second["id"]]}}
            )
        }
        assert len(account_labels) == 2
