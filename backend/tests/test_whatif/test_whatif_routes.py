"""Tests for What-If API routes."""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app import create_app
from app.market_data.symbol_mapper import (
    get_default_symbol_mappings,
)
from config import TestingConfig


@pytest.fixture
def app(patch_minio):
    application = create_app(TestingConfig)
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean all collections before each test."""
    with app.app_context():
        from app.extensions import mongo

        for col in [
            "users", "trades", "executions",
            "trade_accounts", "tags",
            "market_data_datasets",
            "market_data_import_batches",
        ]:
            mongo.db[col].delete_many({})
    yield


def _register_and_login(client):
    """Helper: register a user and return JWT token."""
    client.post(
        "/api/auth/register",
        json={
            "username": "wiuser",
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={
            "username": "wiuser",
            "password": "TestPass123!",
        },
    )
    return resp.get_json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _update_symbol_mappings(client, token, symbol_mappings):
    """Persist symbol mappings for the authenticated test user."""
    response = client.put(
        "/api/auth/symbol-mappings",
        json={"symbol_mappings": symbol_mappings},
        headers=_auth(token),
    )
    assert response.status_code == 200


def _update_market_data_mappings(
    client, token, market_data_mappings
):
    """Persist market-data mappings for the authenticated test user."""
    response = client.put(
        "/api/auth/market-data-mappings",
        json={"market_data_mappings": market_data_mappings},
        headers=_auth(token),
    )
    assert response.status_code == 200


def _update_whatif_target_r_multiple(
    client, token, whatif_target_r_multiple
):
    """Persist the default What-if target R-multiple."""
    response = client.put(
        "/api/auth/whatif-target-r-multiple",
        json={
            "whatif_target_r_multiple": (
                whatif_target_r_multiple
            )
        },
        headers=_auth(token),
    )
    assert response.status_code == 200


def _create_trade(client, token, **overrides):
    """Create a trade and return its JSON."""
    data = {
        "symbol": "MES",
        "side": "Long",
        "total_quantity": 1,
        "entry_price": 5000.0,
        "exit_price": 4990.0,
        "entry_time": "2026-01-05T10:00:00",
        "exit_time": "2026-01-05T10:05:00",
        "initial_risk": 50.0,
    }
    data.update(overrides)
    resp = client.post(
        "/api/trades", json=data, headers=_auth(token)
    )
    return resp.get_json()["trade"]


def _set_wish_stop(client, token, trade_id, price):
    """Set wish_stop_price on a trade."""
    return client.put(
        f"/api/trades/{trade_id}",
        json={"wish_stop_price": price},
        headers=_auth(token),
    )


def _tick_row(
    timestamp: datetime,
    last_price: float,
    *,
    bid_price: float | None = None,
    ask_price: float | None = None,
    size: int = 1,
) -> dict:
    """Build a raw tick row for stored market-data tests."""

    return {
        "timestamp": timestamp,
        "last_price": last_price,
        "bid_price": bid_price
        if bid_price is not None
        else last_price - 0.25,
        "ask_price": ask_price
        if ask_price is not None
        else last_price + 0.25,
        "size": size,
    }


# ---- Stop Analysis ----

class TestStopAnalysis:
    """Tests for GET /api/whatif/stop-analysis."""

    def test_empty_when_no_wicked_out(self, client):
        """Returns zero count when no wicked-out trades."""
        token = _register_and_login(client)
        resp = client.get(
            "/api/whatif/stop-analysis?symbol=MES",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 0
        assert data["confidence_intervals"] == {
            "mean": {"lower": 0.0, "upper": 0.0},
            "median": {"lower": 0.0, "upper": 0.0},
            "p75": {"lower": 0.0, "upper": 0.0},
            "p90": {"lower": 0.0, "upper": 0.0},
            "p95": {"lower": 0.0, "upper": 0.0},
            "iqr": {"lower": 0.0, "upper": 0.0},
        }
        assert "ci_lower" not in data
        assert "ci_upper" not in data

    def test_analysis_with_wicked_out_trade(self, client):
        """Computes R-normalized overshoot correctly."""
        token = _register_and_login(client)
        # Loser: entry=5000, exit=4990 => lost 10 pts
        trade = _create_trade(client, token)
        tid = trade["id"]
        # Set wish_stop_price at 4985 (5 pts below exit)
        _set_wish_stop(client, token, tid, 4985.0)

        resp = client.get(
            "/api/whatif/stop-analysis?symbol=MES",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        # overshoot_R = |4990-4985| / |5000-4990| = 5/10 = 0.5
        assert data["mean"] == 0.5
        assert data["median"] == 0.5
        assert data["confidence_intervals"] == {
            "mean": {"lower": 0.5, "upper": 0.5},
            "median": {"lower": 0.5, "upper": 0.5},
            "p75": {"lower": 0.5, "upper": 0.5},
            "p90": {"lower": 0.5, "upper": 0.5},
            "p95": {"lower": 0.5, "upper": 0.5},
            "iqr": {"lower": 0.0, "upper": 0.0},
        }
        assert "ci_lower" not in data
        assert "ci_upper" not in data
        assert len(data["details"]) == 1

    def test_analysis_without_symbol_aggregates_matching_trades(
        self, client
    ):
        """Returns combined stop analysis when symbol is omitted."""

        token = _register_and_login(client)
        mes_trade = _create_trade(client, token, symbol="MES")
        mnq_trade = _create_trade(
            client,
            token,
            symbol="MNQ",
            entry_price=20000.0,
            exit_price=19990.0,
        )
        _set_wish_stop(client, token, mes_trade["id"], 4985.0)
        _set_wish_stop(client, token, mnq_trade["id"], 19985.0)

        resp = client.get(
            "/api/whatif/stop-analysis",
            headers=_auth(token),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2
        assert data["mean"] == 0.5
        assert {detail["symbol"] for detail in data["details"]} == {
            "MES",
            "MNQ",
        }

    def test_excludes_breakeven_trades(self, client):
        """Skips trades where entry == exit (zero denominator)."""
        token = _register_and_login(client)
        trade = _create_trade(
            client, token,
            exit_price=5000.0,  # breakeven
        )
        _set_wish_stop(client, token, trade["id"], 4995.0)

        resp = client.get(
            "/api/whatif/stop-analysis?symbol=MES",
            headers=_auth(token),
        )
        data = resp.get_json()
        assert data["count"] == 0

    def test_requires_auth(self, client):
        """Returns 401 without token."""
        resp = client.get(
            "/api/whatif/stop-analysis?symbol=MES"
        )
        assert resp.status_code == 401


# ---- Wicked-Out Trades ----

class TestWickedOutTrades:
    """Tests for GET /api/whatif/wicked-out-trades."""

    def test_empty_list(self, client):
        """Returns empty list when no wicked-out trades."""
        token = _register_and_login(client)
        resp = client.get(
            "/api/whatif/wicked-out-trades",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trades"] == []

    def test_returns_wicked_out_trade(self, client):
        """Lists wicked-out trade with fields."""
        token = _register_and_login(client)
        trade = _create_trade(client, token)
        _set_wish_stop(
            client, token, trade["id"], 4985.0
        )

        resp = client.get(
            "/api/whatif/wicked-out-trades",
            headers=_auth(token),
        )
        data = resp.get_json()
        assert len(data["trades"]) == 1
        t = data["trades"][0]
        assert t["symbol"] == "MES"
        assert t["wish_stop_price"] == 4985.0
        assert "has_tick_data" in t

    def test_filters_by_symbol(self, client):
        """Filters by symbol parameter."""
        token = _register_and_login(client)
        trade_mes = _create_trade(
            client, token, symbol="MES"
        )
        trade_mnq = _create_trade(
            client, token, symbol="MNQ",
            entry_price=20000, exit_price=19990,
        )
        _set_wish_stop(
            client, token, trade_mes["id"], 4985.0
        )
        _set_wish_stop(
            client, token, trade_mnq["id"], 19985.0
        )

        resp = client.get(
            "/api/whatif/wicked-out-trades?symbol=MES",
            headers=_auth(token),
        )
        data = resp.get_json()
        assert len(data["trades"]) == 1
        assert data["trades"][0]["symbol"] == "MES"

    def test_reports_tick_data_availability(
        self, client, seed_market_data_dataset
    ):
        """Wicked-out trades report raw tick availability."""

        token = _register_and_login(client)
        trade = _create_trade(client, token)
        _set_wish_stop(
            client, token, trade["id"], 4985.0
        )

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="ticks",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 0, tzinfo=timezone.utc
                    ),
                    5000.0,
                )
            ],
        )

        resp = client.get(
            "/api/whatif/wicked-out-trades?symbol=MES",
            headers=_auth(token),
        )
        assert resp.status_code == 200

        trade_summary = resp.get_json()["trades"][0]
        assert trade_summary["id"] == trade["id"]
        assert trade_summary["has_tick_data"] is True


# ---- Simulation ----

class TestSimulate:
    """Tests for POST /api/whatif/simulate."""

    def test_requires_r_widening(self, client):
        """Returns 400 if r_widening is missing."""
        token = _register_and_login(client)
        resp = client.post(
            "/api/whatif/simulate",
            json={},
            headers=_auth(token),
        )
        assert resp.status_code == 400

    def test_rejects_invalid_r_widening(self, client):
        """Returns 400 for negative r_widening."""
        token = _register_and_login(client)
        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": -1},
            headers=_auth(token),
        )
        assert resp.status_code == 400

    def test_rejects_invalid_replay_mode(self, client):
        """Returns 400 for an unsupported replay mode."""
        token = _register_and_login(client)
        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5, "replay_mode": "foo"},
            headers=_auth(token),
        )
        assert resp.status_code == 400

    def test_no_trades_returns_empty(self, client):
        """Returns zeros when no trades match."""
        token = _register_and_login(client)
        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trades_total"] == 0
        assert data["original"]["total_pnl"] == 0
        assert data["original"]["expectancy_r"] is None

    def test_winner_keeps_pnl(self, client):
        """Winners keep original P&L unchanged."""
        token = _register_and_login(client)
        _create_trade(
            client, token,
            exit_price=5010.0,  # winner
        )

        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )
        data = resp.get_json()
        assert data["trades_total"] == 1
        original = data["original"]["total_pnl"]
        whatif = data["what_if"]["total_pnl"]
        assert original == whatif  # winner unchanged
        assert data["original"]["expectancy_r"] == 1.0
        assert data["what_if"]["expectancy_r"] == 0.67
        detail = data["details"][0]
        assert detail["symbol"] == "MES"
        assert detail["side"] == "Long"
        assert detail["status"] == "winner"
        assert detail["target_source"] is None
        assert detail["original_r"] == 1.0
        assert detail["new_r"] == 0.67
        assert detail["change_r"] == -0.33
        assert "entry_time" in detail

    def test_winner_r_multiple_includes_fees(self, client):
        """Winner R uses initial risk plus fees before and after widening."""
        token = _register_and_login(client)
        _create_trade(
            client,
            token,
            exit_price=5024.0,
            initial_risk=100.0,
            fee=10.0,
        )

        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["original"]["expectancy_r"] == 1.0
        assert data["what_if"]["expectancy_r"] == 0.69
        detail = data["details"][0]
        assert detail["original_r"] == 1.0
        assert detail["new_r"] == 0.69
        assert detail["change_r"] == -0.31

    def test_loser_without_target_uses_default_derived_target(
        self, client, seed_market_data_dataset
    ):
        """Losers without target_price use the default target R-multiple."""
        token = _register_and_login(client)
        _create_trade(client, token)
        seed_market_data_dataset(
            symbol="MES",
            dataset_type="candles",
            timeframe="1m",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5021.0,
                    "low": 4986.0,
                    "close": 5018.0,
                    "volume": 2,
                }
            ],
        )

        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["trades_converted"] == 1
        detail = data["details"][0]
        assert detail["status"] == "simulated"
        assert detail["target_source"] == "derived"
        assert detail["new_pnl"] == 100.0
        assert detail["original_r"] == -1.0
        assert detail["new_r"] == 1.33
        assert detail["change_r"] == 2.33

    def test_loser_without_target_derived_target_uses_original_risk_for_short_trade(
        self, client, seed_market_data_dataset
    ):
        """Derived targets use original risk and correct short direction."""
        token = _register_and_login(client)
        _create_trade(
            client,
            token,
            side="Short",
            entry_price=5000.0,
            exit_price=5010.0,
            initial_risk=50.0,
            entry_time="2026-01-05T10:00:00+00:00",
            exit_time="2026-01-05T10:05:00+00:00",
        )
        seed_market_data_dataset(
            symbol="MES",
            dataset_type="candles",
            timeframe="1m",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5014.0,
                    "low": 4979.0,
                    "close": 4981.0,
                    "volume": 2,
                }
            ],
        )

        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )

        assert resp.status_code == 200
        detail = resp.get_json()["details"][0]
        assert detail["status"] == "simulated"
        assert detail["target_source"] == "derived"
        assert detail["new_pnl"] == 100.0

    def test_invalid_explicit_target_falls_back_to_derived_target(
        self, client, seed_market_data_dataset
    ):
        """Targets on the wrong side of entry are ignored during simulation."""
        token = _register_and_login(client)
        loser = _create_trade(client, token)
        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"target_price": 4995.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="candles",
            timeframe="1m",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5021.0,
                    "low": 4986.0,
                    "close": 5018.0,
                    "volume": 2,
                }
            ],
        )

        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )

        assert resp.status_code == 200
        detail = resp.get_json()["details"][0]
        assert detail["status"] == "simulated"
        assert detail["target_source"] == "derived"
        assert detail["new_pnl"] == 100.0

    def test_loser_without_target_and_without_usable_risk_is_skipped(
        self, client
    ):
        """Trades without target and usable initial risk are skipped distinctly."""
        token = _register_and_login(client)
        loser = _create_trade(client, token)
        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"initial_risk": 0.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )

        assert resp.status_code == 200
        detail = resp.get_json()["details"][0]
        assert detail["status"] == "no_target_risk"
        assert detail["target_source"] is None

    def test_missing_market_data_skips_derived_target_trades_as_no_data(
        self, client
    ):
        """Derived-target trades without replay data are still labeled no_data."""
        token = _register_and_login(client)
        _create_trade(
            client,
            token,
            entry_time="2026-02-04T14:30:00",
            exit_time="2026-02-04T14:35:00",
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        skipped_details = [
            detail for detail in data["details"]
            if detail["status"] == "no_data"
        ]
        assert skipped_details
        assert skipped_details[0]["target_source"] == "derived"

    def test_profit_factor_includes_fee_only_breakeven(
        self, client, app
    ):
        """Net profit factor includes gross-zero negative-net trades."""
        token = _register_and_login(client)
        winner = _create_trade(
            client, token,
            exit_price=5010.0,
            initial_risk=50.0,
        )
        loser = _create_trade(
            client, token,
            exit_price=4990.0,
            initial_risk=50.0,
        )
        breakeven = _create_trade(
            client, token,
            exit_price=5000.0,
            initial_risk=50.0,
        )

        with app.app_context():
            from app.extensions import mongo

            mongo.db.trades.update_one(
                {"_id": ObjectId(breakeven["id"] )},
                {"$set": {"gross_pnl": 0.0, "net_pnl": -2.0, "fee": 2.0}},
            )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        data = resp.get_json()
        expected_pf = round(
            winner["net_pnl"]
            / abs(loser["net_pnl"] + (-2.0)),
            2,
        )
        assert data["original"]["profit_factor"] == expected_pf
        assert data["what_if"]["profit_factor"] == expected_pf

    def test_winners_are_skipped_and_converted_are_not_simulated(
        self, client, app, seed_market_data_dataset
    ):
        """Winner trades count as skipped; converted trades do not."""
        token = _register_and_login(client)
        _create_trade(
            client, token,
            exit_price=5010.0,
        )
        loser = _create_trade(client, token)

        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"target_price": 5005.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="candles",
            timeframe="1m",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5006.0,
                    "low": 4990.0,
                    "close": 5004.0,
                    "volume": 3,
                },
            ],
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["trades_total"] == 2
        assert data["trades_converted"] == 1
        assert data["trades_simulated"] == 0
        assert data["trades_skipped"] == 1

        winner_detail = next(
            d for d in data["details"]
            if d["status"] == "winner"
        )
        converted_detail = next(
            d for d in data["details"]
            if d["trade_id"] == loser["id"]
        )
        assert winner_detail["converted"] is False
        assert converted_detail["converted"] is True

    def test_market_replay_can_convert_with_smaller_widening_than_wish_stop(
        self, client, app, seed_market_data_dataset
    ):
        """Conversion must be based on tick replay, not wish-stop alone."""
        token = _register_and_login(client)
        loser = _create_trade(client, token)

        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={
                "wish_stop_price": 4985.0,
                "target_price": 5005.0,
            },
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="ticks",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 0, tzinfo=timezone.utc
                    ),
                    5000.0,
                ),
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 0, 30, tzinfo=timezone.utc
                    ),
                    4986.5,
                ),
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 1, tzinfo=timezone.utc
                    ),
                    5006.0,
                ),
            ],
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.4, "replay_mode": "tick"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["trades_converted"] == 1
        assert data["trades_simulated"] == 0
        detail = data["details"][0]
        assert detail["trade_id"] == loser["id"]
        assert detail["converted"] is True
        assert detail["target_source"] == "explicit"
        assert detail["new_pnl"] > 0

    def test_short_trade_stop_hit_is_replayed_from_ticks(
        self, client, seed_market_data_dataset
    ):
        """Short trades stop out when ticks reach the widened stop first."""

        token = _register_and_login(client)
        loser = _create_trade(
            client,
            token,
            side="Short",
            entry_price=5000.0,
            exit_price=5010.0,
            initial_risk=50.0,
        )

        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"target_price": 4995.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="ticks",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 0, tzinfo=timezone.utc
                    ),
                    5000.0,
                ),
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 1, tzinfo=timezone.utc
                    ),
                    5015.0,
                ),
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 2, tzinfo=timezone.utc
                    ),
                    4994.0,
                ),
            ],
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5, "replay_mode": "tick"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        data = resp.get_json()
        detail = data["details"][0]
        assert data["trades_converted"] == 0
        assert data["trades_simulated"] == 1
        assert detail["trade_id"] == loser["id"]
        assert detail["status"] == "simulated"
        assert detail["converted"] is False
        assert detail["target_source"] == "explicit"
        assert detail["new_pnl"] == -75.0

    def test_default_simulation_uses_ohlc_candles(
        self, client, seed_market_data_dataset
    ):
        """The default replay mode uses 1-minute OHLC candles."""

        token = _register_and_login(client)
        loser = _create_trade(client, token)

        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"target_price": 5005.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="candles",
            timeframe="1m",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5006.0,
                    "low": 4990.0,
                    "close": 5004.0,
                    "volume": 1,
                }
            ],
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        detail = resp.get_json()["details"][0]
        assert detail["trade_id"] == loser["id"]
        assert detail["status"] == "simulated"
        assert detail["converted"] is True
        assert detail["target_source"] == "explicit"

    def test_ohlc_mode_includes_entry_bar_for_mid_bar_entries(
        self, client, seed_market_data_dataset
    ):
        """OHLC replay must include the candle containing the entry time."""

        token = _register_and_login(client)
        loser = _create_trade(
            client,
            token,
            entry_time="2026-01-05T10:00:30",
            exit_time="2026-01-05T10:05:00",
        )

        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"target_price": 5005.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="candles",
            timeframe="1m",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5006.0,
                    "low": 4983.0,
                    "close": 5004.0,
                    "volume": 10,
                },
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            1,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5004.0,
                    "high": 5006.0,
                    "low": 5003.5,
                    "close": 5005.0,
                    "volume": 4,
                },
            ],
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.6, "replay_mode": "ohlc"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        detail = resp.get_json()["details"][0]
        assert detail["trade_id"] == loser["id"]
        assert detail["status"] == "simulated"
        assert detail["converted"] is False
        assert detail["target_source"] == "explicit"
        assert detail["new_pnl"] < 0

    def test_tick_mode_requires_raw_ticks(
        self, client, seed_market_data_dataset
    ):
        """Tick replay skips candle-only days when raw ticks are missing."""

        token = _register_and_login(client)
        loser = _create_trade(client, token)

        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"target_price": 5005.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="candles",
            timeframe="1m",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5006.0,
                    "low": 4990.0,
                    "close": 5004.0,
                    "volume": 1,
                }
            ],
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5, "replay_mode": "tick"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        detail = resp.get_json()["details"][0]
        assert detail["trade_id"] == loser["id"]
        assert detail["status"] == "no_data"
        assert detail["target_source"] == "explicit"

    def test_ticks_before_entry_are_treated_as_no_data(
        self, client, seed_market_data_dataset
    ):
        """Ticks that end before entry time cannot be used for replay."""

        token = _register_and_login(client)
        loser = _create_trade(client, token)

        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"target_price": 5005.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="ticks",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                _tick_row(
                    datetime(
                        2026, 1, 5, 9, 59, 59, tzinfo=timezone.utc
                    ),
                    4998.0,
                )
            ],
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5, "replay_mode": "tick"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        detail = resp.get_json()["details"][0]
        assert detail["trade_id"] == loser["id"]
        assert detail["status"] == "no_data"
        assert detail["target_source"] == "explicit"

    def test_simulate_uses_user_symbol_mapping_point_value(
        self, client, app, seed_market_data_dataset
    ):
        """Simulation replay uses the user's configured point value."""
        token = _register_and_login(client)
        symbol_mappings = get_default_symbol_mappings()
        symbol_mappings["MES"] = {
            "dollar_value_per_point": 10.0,
        }
        _update_symbol_mappings(client, token, symbol_mappings)

        loser = _create_trade(client, token, initial_risk=100.0)
        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"target_price": 5005.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="candles",
            timeframe="1m",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5006.0,
                    "low": 4990.0,
                    "close": 5004.0,
                    "volume": 3,
                },
            ],
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        detail = resp.get_json()["details"][0]
        assert detail["trade_id"] == loser["id"]
        assert detail["new_pnl"] == 50.0
        assert detail["target_source"] == "explicit"

    def test_simulate_replays_with_market_data_mapping(
        self, client, seed_market_data_dataset
    ):
        """Simulation replay resolves candle datasets via market-data mappings."""
        token = _register_and_login(client)
        _update_market_data_mappings(
            client,
            token,
            {"MES": "ES"},
        )

        loser = _create_trade(client, token, initial_risk=100.0)
        update_resp = client.put(
            f"/api/trades/{loser['id']}",
            json={"target_price": 5005.0},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200

        seed_market_data_dataset(
            symbol="ES",
            raw_symbol="ES",
            dataset_type="candles",
            timeframe="1m",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                {
                    "time": int(
                        datetime(
                            2026,
                            1,
                            5,
                            10,
                            0,
                            tzinfo=timezone.utc,
                        ).timestamp()
                    ),
                    "open": 5000.0,
                    "high": 5006.0,
                    "low": 4990.0,
                    "close": 5004.0,
                    "volume": 3,
                },
            ],
        )

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trades_converted"] == 1
        assert data["details"][0]["status"] == "simulated"
        assert data["details"][0]["target_source"] == "explicit"

    def test_simulate_cache_key_includes_whatif_target_r_multiple(
        self, client, seed_market_data_dataset
    ):
        """Changing the default target setting must invalidate cached results."""
        token = _register_and_login(client)
        _create_trade(client, token)

        seed_market_data_dataset(
            symbol="MES",
            dataset_type="ticks",
            trading_day=datetime(2026, 1, 5).date(),
            rows=[
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 0, tzinfo=timezone.utc
                    ),
                    5000.0,
                ),
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 1, tzinfo=timezone.utc
                    ),
                    5011.0,
                ),
                _tick_row(
                    datetime(
                        2026, 1, 5, 10, 2, tzinfo=timezone.utc
                    ),
                    4992.0,
                ),
            ],
        )

        _update_whatif_target_r_multiple(client, token, 1.0)
        first_resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5, "replay_mode": "tick"},
            headers=_auth(token),
        )
        assert first_resp.status_code == 200
        first_detail = first_resp.get_json()["details"][0]
        assert first_detail["target_source"] == "derived"
        assert first_detail["new_pnl"] == 50.0

        _update_whatif_target_r_multiple(client, token, 3.0)
        second_resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.5, "replay_mode": "tick"},
            headers=_auth(token),
        )
        assert second_resp.status_code == 200
        second_detail = second_resp.get_json()["details"][0]
        assert second_detail["target_source"] == "derived"
        assert second_detail["new_pnl"] == -40.0

    def test_simulate_filters_by_tag(self, client, app):
        """Simulation respects the selected tag filter."""
        token = _register_and_login(client)
        tagged_trade = _create_trade(
            client, token, exit_price=5010.0
        )
        _create_trade(client, token)

        with app.app_context():
            from app.extensions import mongo

            tagged_trade_doc = mongo.db.trades.find_one({
                "_id": ObjectId(tagged_trade["id"])
            })
            tag_id = ObjectId()
            mongo.db.tags.insert_one({
                "_id": tag_id,
                "user_id": tagged_trade_doc["user_id"],
                "name": "focus",
            })
            mongo.db.trades.update_one(
                {"_id": ObjectId(tagged_trade["id"] )},
                {"$set": {"tag_ids": [tag_id]}},
            )

        resp = client.post(
            f"/api/whatif/simulate?symbol=MES&tag={tag_id}",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["trades_total"] == 1
        assert data["details"][0]["trade_id"] == tagged_trade["id"]

    def test_requires_auth(self, client):
        """Returns 401 without token."""
        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5},
        )
        assert resp.status_code == 401


# ---- Auto-tag ----

class TestAutoTag:
    """Tests for wicked-out auto-tagging via trade update."""

    def test_wish_stop_adds_tag(self, client):
        """Setting wish_stop_price adds wicked-out tag."""
        token = _register_and_login(client)
        trade = _create_trade(client, token)

        resp = _set_wish_stop(
            client, token, trade["id"], 4985.0
        )
        updated = resp.get_json()["trade"]
        assert updated["wish_stop_price"] == 4985.0

        # Verify wicked-out tag exists
        tags_resp = client.get(
            "/api/tags", headers=_auth(token)
        )
        tags = tags_resp.get_json()["tags"]
        wo_tag = next(
            (t for t in tags if t["name"] == "wicked-out"),
            None,
        )
        assert wo_tag is not None
        assert wo_tag["id"] in updated["tag_ids"]

    def test_clear_wish_stop_removes_tag(self, client):
        """Clearing wish_stop_price removes wicked-out tag."""
        token = _register_and_login(client)
        trade = _create_trade(client, token)
        _set_wish_stop(
            client, token, trade["id"], 4985.0
        )

        # Clear
        resp = client.put(
            f"/api/trades/{trade['id']}",
            json={"wish_stop_price": None},
            headers=_auth(token),
        )
        updated = resp.get_json()["trade"]
        assert updated["wish_stop_price"] is None

        tags_resp = client.get(
            "/api/tags", headers=_auth(token)
        )
        tags = tags_resp.get_json()["tags"]
        wo_tag = next(
            (t for t in tags if t["name"] == "wicked-out"),
            None,
        )
        if wo_tag:
            assert wo_tag["id"] not in updated["tag_ids"]


# ---- Target Price Auto-populate ----

class TestTargetAutoPopulate:
    """Tests for target_price auto-population."""

    def test_winner_gets_target(self, client):
        """Winners auto-set target_price = exit_price."""
        token = _register_and_login(client)
        trade = _create_trade(
            client, token,
            exit_price=5010.0,  # winner
        )
        assert trade["target_price"] == 5010.0

    def test_loser_no_target(self, client):
        """Losers do not auto-set target_price."""
        token = _register_and_login(client)
        trade = _create_trade(client, token)
        assert trade["target_price"] is None


# ---- Symbols Endpoint ----

class TestSymbolsEndpoint:
    """Tests for GET /api/trades/symbols."""

    def test_returns_distinct_symbols(self, client):
        """Returns sorted distinct symbols."""
        token = _register_and_login(client)
        _create_trade(client, token, symbol="MES")
        _create_trade(client, token, symbol="MNQ",
                       entry_price=20000, exit_price=19990)

        resp = client.get(
            "/api/trades/symbols",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "MES" in data["symbols"]
        assert "MNQ" in data["symbols"]

    def test_empty_when_no_trades(self, client):
        """Returns empty list when no trades."""
        token = _register_and_login(client)
        resp = client.get(
            "/api/trades/symbols",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["symbols"] == []
