"""Tests that workspace mode isolates trade-facing reads and writes."""

from datetime import datetime, timedelta

import pytest
from bson import ObjectId

from app.extensions import mongo
from app.utils.datetime_utils import utc_now


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clear collections used by these tests."""
    with app.app_context():
        for name in (
            "users",
            "workspace_modes",
            "trade_accounts",
            "trades",
            "executions",
            "tags",
            "market_data_datasets",
            "market_data_import_batches",
        ):
            mongo.db[name].delete_many({})


def _register(client):
    """Create a user and return its id and auth header."""
    client.post(
        "/api/auth/register",
        json={
            "username": "workspace-isolation",
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={
            "username": "workspace-isolation",
            "password": "TestPass123!",
        },
    )
    assert login.status_code == 200
    user_id = login.json["user"]["id"]
    return user_id, {"Authorization": f"Bearer {login.json['token']}"}


def _seed_account_and_trade(
    user_id,
    *,
    account_name,
    workspace_mode=None,
    net_pnl=10.0,
    tag_ids=None,
):
    """Insert an account, its closed trade, and one execution."""
    owner = ObjectId(user_id)
    account_id = ObjectId()
    trade_id = ObjectId()
    now = utc_now()
    account = {
        "_id": account_id,
        "user_id": owner,
        "account_name": account_name,
        "display_name": account_name,
        "status": "active",
        "source_platform": "manual",
        "created_at": now,
        "updated_at": now,
    }
    if workspace_mode is not None:
        account["workspace_mode"] = workspace_mode
    trade = {
        "_id": trade_id,
        "user_id": owner,
        "trade_account_id": account_id,
        "import_batch_id": None,
        "symbol": "MES",
        "raw_symbol": "MES",
        "side": "Long",
        "total_quantity": 1,
        "max_quantity": 1,
        "avg_entry_price": 5000.0,
        "avg_exit_price": 5002.0,
        "gross_pnl": net_pnl,
        "fee": 0.0,
        "net_pnl": net_pnl,
        "initial_risk": 2.0,
        "entry_time": now - timedelta(minutes=5),
        "exit_time": now,
        "holding_time_seconds": 300,
        "execution_count": 1,
        "status": "closed",
        "tag_ids": tag_ids or [],
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    execution = {
        "_id": ObjectId(),
        "user_id": owner,
        "trade_account_id": account_id,
        "trade_id": trade_id,
        "import_batch_id": None,
        "symbol": "MES",
        "raw_symbol": "MES",
        "side": "Buy",
        "quantity": 1,
        "price": 5000.0,
        "timestamp": now - timedelta(minutes=5),
    }
    mongo.db.trade_accounts.insert_one(account)
    mongo.db.trades.insert_one(trade)
    mongo.db.executions.insert_one(execution)
    return account, trade, execution


def _set_mode(client, headers, active_mode):
    response = client.put(
        "/api/workspace/mode",
        json={"active_mode": active_mode},
        headers=headers,
    )
    assert response.status_code == 200


def test_legacy_accounts_default_to_real_and_reads_follow_active_mode(
    app, client,
):
    user_id, headers = _register(client)
    with app.app_context():
        legacy, legacy_trade, legacy_execution = _seed_account_and_trade(
            user_id,
            account_name="Legacy account",
            net_pnl=10.0,
        )
        real, real_trade, real_execution = _seed_account_and_trade(
            user_id,
            account_name="Explicit Real",
            workspace_mode="real",
            net_pnl=20.0,
        )
        backtest, backtest_trade, backtest_execution = (
            _seed_account_and_trade(
                user_id,
                account_name="Backtest",
                workspace_mode="backtest",
                net_pnl=1000.0,
            )
        )

    accounts = client.get("/api/accounts", headers=headers)
    trades = client.get("/api/trades", headers=headers)
    executions = client.get("/api/executions", headers=headers)
    summary = client.get("/api/analytics/summary", headers=headers)
    calendar = client.get("/api/analytics/calendar", headers=headers)
    assert accounts.status_code == 200
    assert {item["id"] for item in accounts.json["accounts"]} == {
        str(legacy["_id"]),
        str(real["_id"]),
    }
    assert trades.status_code == 200
    assert {item["id"] for item in trades.json["trades"]} == {
        str(legacy_trade["_id"]),
        str(real_trade["_id"]),
    }
    assert executions.status_code == 200
    assert {
        item["id"] for item in executions.json["executions"]
    } == {str(legacy_execution["_id"]), str(real_execution["_id"])}
    assert summary.status_code == 200
    assert summary.json["total_trades"] == 2
    assert summary.json["total_net_pnl"] == 30.0
    assert calendar.status_code == 200
    assert sum(day["trade_count"] for day in calendar.json) == 2

    _set_mode(client, headers, "backtest")
    accounts = client.get("/api/accounts", headers=headers)
    trades = client.get("/api/trades", headers=headers)
    executions = client.get("/api/executions", headers=headers)
    summary = client.get("/api/analytics/summary", headers=headers)
    calendar = client.get("/api/analytics/calendar", headers=headers)
    assert {item["id"] for item in accounts.json["accounts"]} == {
        str(backtest["_id"])
    }
    assert {item["id"] for item in trades.json["trades"]} == {
        str(backtest_trade["_id"])
    }
    assert {item["id"] for item in executions.json["executions"]} == {
        str(backtest_execution["_id"])
    }
    assert summary.json["total_trades"] == 1
    assert summary.json["total_net_pnl"] == 1000.0
    assert sum(day["trade_count"] for day in calendar.json) == 1


def test_backtest_mode_rejects_manual_trade_and_import_writes(client):
    _, headers = _register(client)
    _set_mode(client, headers, "backtest")

    manual = client.post(
        "/api/trades", json={}, headers=headers
    )
    finalize = client.post(
        "/api/imports/finalize", json={}, headers=headers
    )
    upload = client.post(
        "/api/imports/upload", headers=headers
    )

    assert manual.status_code == 403
    assert finalize.status_code == 403
    assert upload.status_code == 403
    assert manual.json["error"]["code"] == "FORBIDDENERROR"
    assert finalize.json["error"]["code"] == "FORBIDDENERROR"
    assert upload.json["error"]["code"] == "FORBIDDENERROR"


def test_what_if_results_follow_active_workspace_mode(app, client):
    user_id, headers = _register(client)
    with app.app_context():
        tag_id = ObjectId()
        mongo.db.tags.insert_one(
            {
                "_id": tag_id,
                "user_id": ObjectId(user_id),
                "name": "wicked-out",
            }
        )
        _, real_trade, _ = _seed_account_and_trade(
            user_id,
            account_name="Real what-if",
            net_pnl=-10.0,
            tag_ids=[tag_id],
        )
        _, backtest_trade, _ = _seed_account_and_trade(
            user_id,
            account_name="Backtest what-if",
            workspace_mode="backtest",
            net_pnl=-100.0,
            tag_ids=[tag_id],
        )

    real_result = client.get(
        "/api/whatif/wicked-out-trades", headers=headers
    )
    assert {item["id"] for item in real_result.json["trades"]} == {
        str(real_trade["_id"])
    }

    _set_mode(client, headers, "backtest")
    backtest_result = client.get(
        "/api/whatif/wicked-out-trades", headers=headers
    )
    assert {item["id"] for item in backtest_result.json["trades"]} == {
        str(backtest_trade["_id"])
    }
