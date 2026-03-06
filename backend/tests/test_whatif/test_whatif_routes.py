"""Tests for What-If API routes."""

import pytest

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
        assert "entry_time" in detail

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
        assert d["status"] in ("no_target", "no_risk")

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
