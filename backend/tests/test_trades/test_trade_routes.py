"""Tests for trade API routes."""

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
    resp = _create_trade(client, token, fee=0.78)
    assert resp.status_code == 201
    trade = resp.get_json()["trade"]
    assert trade["symbol"] == "MES"
    assert trade["side"] == "Long"
    assert trade["gross_pnl"] == 50.0
    assert trade["fee"] == 0.78
    assert trade["net_pnl"] == 49.22


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

    resp = client.put(
        f"/api/trades/{trade_id}",
        json={"fee": 1.50},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    trade = resp.get_json()["trade"]
    assert trade["fee"] == 1.50
    assert trade["net_pnl"] == 48.50


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


def test_soft_delete_and_restore(client):
    token = _register_and_login(client)
    create_resp = _create_trade(client, token)
    trade_id = create_resp.get_json()["trade"]["id"]

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

    # Restore
    resp = client.post(
        f"/api/trades/{trade_id}/restore",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200

    # Should appear again
    resp = client.get(
        "/api/trades",
        headers=_auth_header(token),
    )
    assert resp.get_json()["total"] == 1


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
