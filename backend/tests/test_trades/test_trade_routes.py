"""Tests for trade API routes."""

from datetime import date

import pytest

from app import create_app
from app.market_data.symbol_mapper import (
    get_default_symbol_mappings,
)
from app.whatif.cache import _sim_cache
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
        ]:
            mongo.db[col].delete_many({})
    yield


def _register_and_login(client):
    """Helper: register a user and return JWT token."""
    client.post(
        "/api/auth/register",
        json={
            "username": "tradeuser",
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={
            "username": "tradeuser",
            "password": "TestPass123!",
        },
    )
    return resp.get_json()["token"]


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _update_symbol_mappings(client, token, symbol_mappings):
    """Persist symbol mappings for the authenticated test user."""
    response = client.put(
        "/api/auth/symbol-mappings",
        json={"symbol_mappings": symbol_mappings},
        headers=_auth_header(token),
    )
    assert response.status_code == 200


def _update_market_data_mappings(
    client, token, market_data_mappings
):
    """Persist market-data mappings for the authenticated test user."""
    response = client.put(
        "/api/auth/market-data-mappings",
        json={"market_data_mappings": market_data_mappings},
        headers=_auth_header(token),
    )
    assert response.status_code == 200


def _create_trade(client, token, **overrides):
    """Helper to create a trade with defaults."""
    data = {
        "symbol": "MES",
        "side": "Long",
        "total_quantity": 1,
        "entry_price": 5000.0,
        "exit_price": 5010.0,
        "entry_time": "2026-01-01T10:00:00",
        "exit_time": "2026-01-01T10:05:00",
    }
    data.update(overrides)
    return client.post(
        "/api/trades",
        json=data,
        headers=_auth_header(token),
    )


def test_create_manual_trade(client):
    token = _register_and_login(client)
    _sim_cache["stale"] = (0.0, {"cached": True})
    resp = _create_trade(client, token, fee=0.78)
    assert resp.status_code == 201
    trade = resp.get_json()["trade"]
    assert trade["symbol"] == "MES"
    assert trade["side"] == "Long"
    assert trade["gross_pnl"] == 50.0
    assert trade["fee"] == 0.78
    assert trade["net_pnl"] == 49.22
    assert trade["initial_risk"] == 0.0
    assert _sim_cache == {}


def test_create_manual_trade_loser_sets_initial_risk(client):
    token = _register_and_login(client)
    resp = _create_trade(
        client,
        token,
        entry_price=5010.0,
        exit_price=5000.0,
        fee=1.0,
    )

    assert resp.status_code == 201
    trade = resp.get_json()["trade"]
    assert trade["net_pnl"] < 0
    assert trade["gross_pnl"] < 0
    assert trade["initial_risk"] == abs(trade["gross_pnl"])


def test_create_manual_trade_uses_user_symbol_mapping_point_value(client):
    token = _register_and_login(client)
    symbol_mappings = get_default_symbol_mappings()
    symbol_mappings["MES"] = {
        "dollar_value_per_point": 10.0,
    }
    _update_symbol_mappings(client, token, symbol_mappings)

    resp = _create_trade(client, token, fee=0.78)

    assert resp.status_code == 201
    trade = resp.get_json()["trade"]
    assert trade["gross_pnl"] == 100.0
    assert trade["net_pnl"] == 99.22


def test_list_trades_empty(client):
    token = _register_and_login(client)
    resp = client.get(
        "/api/trades",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["trades"] == []
    assert data["total"] == 0


def test_list_trades_with_data(client):
    token = _register_and_login(client)
    _create_trade(client, token)
    resp = client.get(
        "/api/trades",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert len(data["trades"]) == 1


def test_list_trades_market_data_cached_uses_explicit_mapping(
    client,
    seed_market_data_dataset,
):
    token = _register_and_login(client)
    _update_market_data_mappings(
        client,
        token,
        {"MES": "ES"},
    )
    _create_trade(
        client,
        token,
        entry_time="2026-01-05T10:00:00",
        exit_time="2026-01-05T10:05:00",
    )
    seed_market_data_dataset(
        symbol="ES",
        raw_symbol="ES",
        dataset_type="candles",
        timeframe="5m",
        trading_day=date(2026, 1, 5),
        rows=[
            {
                "time": int(1736071200),
                "open": 5000.0,
                "high": 5006.0,
                "low": 4998.0,
                "close": 5004.0,
                "volume": 10,
            }
        ],
    )

    resp = client.get(
        "/api/trades",
        headers=_auth_header(token),
    )

    assert resp.status_code == 200
    assert resp.get_json()["trades"][0]["market_data_cached"] is True


def test_list_trades_date_to_includes_selected_day(client):
    token = _register_and_login(client)
    _create_trade(
        client,
        token,
        entry_time="2026-02-04T14:30:00",
        exit_time="2026-02-04T14:45:00",
    )

    resp = client.get(
        "/api/trades?date_from=2026-02-04&date_to=2026-02-04",
        headers=_auth_header(token),
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert len(data["trades"]) == 1


def test_list_trades_date_to_excludes_following_day(client):
    token = _register_and_login(client)
    _create_trade(
        client,
        token,
        entry_time="2026-02-04T10:00:00",
        exit_time="2026-02-04T10:05:00",
    )
    _create_trade(
        client,
        token,
        entry_time="2026-02-05T10:00:00",
        exit_time="2026-02-05T10:05:00",
    )

    resp = client.get(
        "/api/trades?date_from=2026-02-04&date_to=2026-02-04",
        headers=_auth_header(token),
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert len(data["trades"]) == 1
    assert data["trades"][0]["entry_time"].startswith("2026-02-04")


def test_get_trade_detail(client):
    token = _register_and_login(client)
    create_resp = _create_trade(
        client, token, side="Short",
        total_quantity=2,
        entry_price=5050.0,
        exit_price=5040.0,
    )
    trade_id = create_resp.get_json()["trade"]["id"]

    resp = client.get(
        f"/api/trades/{trade_id}",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["trade"]["side"] == "Short"
    assert data["trade"]["total_quantity"] == 2


def test_update_trade_fee(client):
    token = _register_and_login(client)
    create_resp = _create_trade(client, token)
    trade_id = create_resp.get_json()["trade"]["id"]
    _sim_cache["stale"] = (0.0, {"cached": True})

    resp = client.put(
        f"/api/trades/{trade_id}",
        json={"fee": 1.50},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    trade = resp.get_json()["trade"]
    assert trade["fee"] == 1.50
    assert trade["net_pnl"] == 48.50
    assert _sim_cache == {}


def test_update_trade_initial_risk(client):
    token = _register_and_login(client)
    create_resp = _create_trade(client, token)
    trade_id = create_resp.get_json()["trade"]["id"]

    resp = client.put(
        f"/api/trades/{trade_id}",
        json={"initial_risk": 120.0},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    trade = resp.get_json()["trade"]
    assert trade["initial_risk"] == 120.0


def test_update_trade_notes(client):
    token = _register_and_login(client)
    create_resp = _create_trade(client, token)
    trade_id = create_resp.get_json()["trade"]["id"]

    resp = client.put(
        f"/api/trades/{trade_id}",
        json={
            "post_trade_notes": "Good entry.",
            "strategy": "Breakout",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    trade = resp.get_json()["trade"]
    assert trade["post_trade_notes"] == "Good entry."
    assert trade["strategy"] == "Breakout"


def test_delete_trade_removes_completely(client):
    token = _register_and_login(client)
    create_resp = _create_trade(client, token)
    trade_id = create_resp.get_json()["trade"]["id"]
    _sim_cache["stale"] = (0.0, {"cached": True})

    # Delete
    resp = client.delete(
        f"/api/trades/{trade_id}",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200

    # Should not appear in list
    resp = client.get(
        "/api/trades",
        headers=_auth_header(token),
    )
    assert resp.get_json()["total"] == 0
    assert _sim_cache == {}

    # Trade detail is gone
    resp = client.get(
        f"/api/trades/{trade_id}",
        headers=_auth_header(token),
    )
    assert resp.status_code == 404

    # Restore also fails because the trade was removed
    resp = client.post(
        f"/api/trades/{trade_id}/restore",
        headers=_auth_header(token),
    )
    assert resp.status_code == 404


def test_get_nonexistent_trade(client):
    token = _register_and_login(client)
    resp = client.get(
        "/api/trades/000000000000000000000000",
        headers=_auth_header(token),
    )
    assert resp.status_code == 404


def test_create_trade_missing_fields(client):
    token = _register_and_login(client)
    resp = client.post(
        "/api/trades",
        json={"symbol": "MES"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 400


def test_create_trade_without_auth(client):
    resp = client.post(
        "/api/trades",
        json={
            "symbol": "MES",
            "side": "Long",
            "total_quantity": 1,
            "entry_price": 5000.0,
            "exit_price": 5010.0,
            "entry_time": "2026-01-01T10:00:00",
            "exit_time": "2026-01-01T10:05:00",
        },
    )
    assert resp.status_code == 401
