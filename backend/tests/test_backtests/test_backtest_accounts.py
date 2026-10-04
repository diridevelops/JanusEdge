"""Backtest account selector and empty trade-list API tests."""

from bson import ObjectId


def _register(client, username):
    registered = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "TestPass123!",
            "timezone": "UTC",
        },
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "TestPass123!"},
    )
    assert login.status_code == 200
    return login.json["user"]["id"], {
        "Authorization": f"Bearer {login.json['token']}"
    }


def _set_mode(client, headers, mode):
    response = client.put(
        "/api/workspace/mode",
        json={"active_mode": mode},
        headers=headers,
    )
    assert response.status_code == 200


def test_accounts_are_one_per_run_mode_separated_and_selectable_with_no_trades(
    app, client, monkeypatch
):
    """Same-range runs remain distinct and Backtest selection has no trades."""
    import app.backtests.service as backtest_service_module

    from app.extensions import mongo
    from app.models.trade_account import create_trade_account_doc

    monkeypatch.setattr(
        backtest_service_module,
        "fetch_instrument_codes",
        lambda: ["EUR-USD"],
    )
    user_id, headers = _register(client, "backtest-account-selector")

    # Both requests use the same instrument and inclusive date range; only
    # accounts are created because preparation remains asynchronous.
    _set_mode(client, headers, "backtest")
    requests = [
        client.post(
            "/api/backtest/runs",
            json={
                "instrument": "EUR-USD",
                "start_date": "2026-01-05",
                "end_date": "2026-01-05",
                "display_timezone": "UTC",
            },
            headers=headers,
        )
        for _ in range(2)
    ]
    assert all(response.status_code == 202 for response in requests)
    runs = [response.json["run"] for response in requests]
    run_ids = {run["id"] for run in runs}
    run_by_id = {run["id"]: run for run in runs}
    account_ids = {run["account_id"] for run in runs}
    assert len(run_ids) == len(account_ids) == 2

    accounts_response = client.get("/api/accounts", headers=headers)
    assert accounts_response.status_code == 200
    backtest_accounts = accounts_response.json["accounts"]
    assert len(backtest_accounts) == 2
    by_run_id = {
        account["backtest_run_id"]: account
        for account in backtest_accounts
    }
    assert set(by_run_id) == run_ids
    assert {account["id"] for account in backtest_accounts} == account_ids
    assert all(
        account["workspace_mode"] == "backtest"
        for account in backtest_accounts
    )

    labels = [
        account.get("display_name") or account["account_name"]
        for account in backtest_accounts
    ]
    assert len(set(labels)) == 2
    assert all(
        "EUR-USD" in label
        and "2026-01-05" in label
        for label in labels
    )

    with app.app_context():
        user_oid = ObjectId(user_id)
        for run in runs:
            assert mongo.db.trade_accounts.count_documents(
                {
                    "user_id": user_oid,
                    "backtest_run_id": ObjectId(run["id"]),
                }
            ) == 1

        # A Real account may share the display label, but it has its own id
        # and account-name key and must remain hidden in Backtest mode.
        real_account = create_trade_account_doc(
            user_id=user_oid,
            account_name="real-account-with-shared-label",
            display_name=labels[0],
            source_platform="manual",
        )
        real_account.update(
            {
                "_id": ObjectId(),
                "workspace_mode": "real",
            }
        )
        mongo.db.trade_accounts.insert_one(real_account)

    backtest_accounts_after_seed = client.get(
        "/api/accounts", headers=headers
    ).json["accounts"]
    assert {account["id"] for account in backtest_accounts_after_seed} == account_ids

    _set_mode(client, headers, "real")
    real_accounts = client.get("/api/accounts", headers=headers)
    assert real_accounts.status_code == 200
    assert [account["id"] for account in real_accounts.json["accounts"]] == [
        str(real_account["_id"])
    ]
    assert real_accounts.json["accounts"][0]["display_name"] == labels[0]
    assert real_accounts.json["accounts"][0]["id"] not in account_ids

    _set_mode(client, headers, "backtest")
    restored_backtest_accounts = client.get(
        "/api/accounts", headers=headers
    ).json["accounts"]
    assert {account["id"] for account in restored_backtest_accounts} == account_ids
    assert str(real_account["_id"]) not in {
        account["id"] for account in restored_backtest_accounts
    }

    for account in restored_backtest_accounts:
        # FilterBar selects by account id. The account response maps that
        # selection to exactly one run, while recording remains unavailable.
        matching_run = run_by_id[account["backtest_run_id"]]
        assert matching_run["account_id"] == account["id"]
        assert matching_run["id"] in run_ids
        trades = client.get(
            f"/api/trades?account={account['id']}", headers=headers
        )
        assert trades.status_code == 200
        assert trades.json["trades"] == []
        assert trades.json["total"] == 0
