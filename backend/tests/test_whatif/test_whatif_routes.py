"""Tests for What-If API routes."""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app import create_app
from config import TestingConfig


@pytest.fixture
def app():
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
            "market_data_cache",
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
        assert "has_ohlc_data" in t

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

    def test_loser_without_target_skipped(self, client):
        """Losers without target_price are skipped."""
        token = _register_and_login(client)
        _create_trade(client, token)  # loser, no target

        resp = client.post(
            "/api/whatif/simulate",
            json={"r_widening": 0.5},
            headers=_auth(token),
        )
        data = resp.get_json()
        assert data["trades_skipped"] >= 1
        d = data["details"][0]
        assert d["status"] in ("no_target", "no_risk", "no_ohlc")
        assert d["original_pnl"] == d["new_pnl"]
        assert d["original_r"] == -1.0
        assert d["new_r"] == -0.67
        assert d["change_r"] == 0.33

    def test_loser_without_target_r_multiple_includes_fees(
        self, client
    ):
        """Skipped losers still report fee-inclusive R values."""
        token = _register_and_login(client)
        _create_trade(
            client,
            token,
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
        detail = data["details"][0]
        assert detail["original_r"] == -0.55
        assert detail["new_r"] == -0.38
        assert detail["change_r"] == 0.17

    def test_missing_market_data_takes_priority_over_no_target(
        self, client
    ):
        """Losers with no target and no cached OHLC are labeled no_ohlc."""
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
            if detail["status"] == "no_ohlc"
        ]
        assert skipped_details

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
        self, client, app
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

        with app.app_context():
            from app.extensions import mongo

            mongo.db.market_data_cache.insert_one({
                "symbol": "MES=F",
                "interval": "1m",
                "date": datetime(2026, 1, 5),
                "ohlc": [
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
                    }
                ],
                "bar_count": 1,
                "fetched_at": datetime(2026, 1, 5),
                "source": "test",
            })

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
        self, client, app
    ):
        """Conversion must be based on OHLC replay, not wish-stop alone."""
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

        with app.app_context():
            from app.extensions import mongo

            mongo.db.market_data_cache.insert_one({
                "symbol": "MES=F",
                "interval": "1m",
                "date": datetime(2026, 1, 5),
                "ohlc": [
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
                        "low": 4986.5,
                        "close": 5004.0,
                    }
                ],
                "bar_count": 1,
                "fetched_at": datetime(2026, 1, 5),
                "source": "test",
            })

        resp = client.post(
            "/api/whatif/simulate?symbol=MES",
            json={"r_widening": 0.4},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["trades_converted"] == 1
        assert data["trades_simulated"] == 0
        detail = data["details"][0]
        assert detail["trade_id"] == loser["id"]
        assert detail["converted"] is True
        assert detail["new_pnl"] > 0

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
