"""Owner-scoped immutable snapshot and replay cursor API tests."""

from datetime import date, datetime, timezone


def _patch_catalog(monkeypatch):
    import app.backtests.service as service_module

    monkeypatch.setattr(
        service_module,
        "fetch_instrument_codes",
        lambda: ["EUR-USD"],
    )


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
    return {"Authorization": f"Bearer {login.json['token']}"}


def _candle(utc_date, minute, price):
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
        "volume": 30 + minute,
    }


class _Provider:
    """Return fixed daily responses and record reads for ownership checks."""

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def fetch_day(self, instrument, utc_date):
        self.calls.append((instrument, utc_date))
        return self.outcomes.get(utc_date, _day_result(utc_date, []))


def _day_result(utc_date, candles):
    return {
        "utc_date": utc_date,
        "outcome": "data" if candles else "empty",
        "candles": candles,
    }


class _Clock:
    def __call__(self):
        return datetime(2026, 12, 1, tzinfo=timezone.utc)


def _create_ready_run(
    app,
    client,
    headers,
    *,
    current_candle_overrides=None,
    next_candle_overrides=None,
    execution_costs=None,
):
    from app.backtests.worker import BacktestWorker

    request = {
        "instrument": "EUR-USD",
        "start_date": "2026-01-05",
        "end_date": "2026-01-07",
        "display_timezone": "UTC",
        "warmup_days": 31,
    }
    if execution_costs is not None:
        request["execution_costs"] = execution_costs
    response = client.post(
        "/api/backtest/runs",
        json=request,
        headers=headers,
    )
    assert response.status_code == 202
    run_id = response.json["run"]["id"]

    jan_5 = date(2026, 1, 5)
    jan_6 = date(2026, 1, 6)
    jan_7 = date(2026, 1, 7)
    dec_5 = date(2025, 12, 5)
    current_candle = _candle(jan_5, 0, 1.1)
    current_candle.update(current_candle_overrides or {})
    next_candle = _candle(jan_5, 1, 1.2)
    next_candle.update(next_candle_overrides or {})
    provider = _Provider(
        {
            dec_5: _day_result(dec_5, [_candle(dec_5, 0, 0.9)]),
            jan_5: _day_result(jan_5, [current_candle, next_candle]),
            jan_6: _day_result(jan_6, []),
            jan_7: _day_result(jan_7, [_candle(jan_7, 0, 1.3)]),
        }
    )
    with app.app_context():
        worker = BacktestWorker(provider=provider, clock=_Clock())
        assert worker.process_one()

    ready = client.get(
        f"/api/backtest/runs/{run_id}", headers=headers
    )
    assert ready.status_code == 200
    assert ready.json["run"]["status"] == "ready"
    return run_id, ready.json["run"], provider


def _saved_cursor(client, headers, run_id):
    response = client.get(
        f"/api/backtest/runs/{run_id}", headers=headers
    )
    assert response.status_code == 200
    return _cursor_values(response.json["run"]["replay_cursor"])


def _cursor_values(cursor):
    """Select the three public cursor fields; timestamps may be additive."""
    return {
        key: cursor[key]
        for key in ("source_candle_index", "time_ms", "revision")
    }


def test_execution_costs_are_fixed_at_creation_and_read_only_in_replay(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "simulation-costs-fixed-owner")
    costs = {
        "total_spread_pips": 1.2,
        "slippage_pips": 0.4,
        "commission_usd_per_lot_per_side": 2.5,
    }
    run_id, run, _ = _create_ready_run(
        app, client, owner, execution_costs=costs
    )

    assert run["execution_costs"] == costs
    state = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert state.status_code == 200
    assert state.json["cost_profile"]["total_spread_pips"] == 1.2
    assert state.json["cost_profile"]["slippage_pips"] == 0.4
    assert state.json["cost_profile"]["commission_usd_per_lot_per_side"] == 2.5

    rejected = client.put(
        f"/api/backtest/runs/{run_id}/simulation/costs",
        json={
            "client_operation_id": "late-cost-edit",
            "expected_revision": 0,
            "total_spread_pips": 0,
            "slippage_pips": 0,
            "commission_usd_per_lot_per_side": 0,
        },
        headers=owner,
    )
    assert rejected.status_code == 409

    after = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    for field in (
        "revision",
        "operation_sequence",
        "total_spread_pips",
        "slippage_pips",
        "commission_usd_per_lot_per_side",
    ):
        assert after.json["cost_profile"][field] == state.json["cost_profile"][field]


def test_available_utc_dates_and_day_candles_are_read_from_owned_snapshot(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "replay-snapshot-owner")
    other_user = _register(client, "replay-snapshot-other")
    run_id, run, provider = _create_ready_run(app, client, owner)

    dates = client.get(
        f"/api/backtest/runs/{run_id}/candle-dates", headers=owner
    )
    assert dates.status_code == 200
    assert dates.json == {
        "dates": ["2025-12-05", "2026-01-05", "2026-01-07"]
    }

    before = client.get(
        f"/api/backtest/runs/{run_id}/candle-dates?before=2026-01-07",
        headers=owner,
    )
    after = client.get(
        f"/api/backtest/runs/{run_id}/candle-dates?after=2026-01-05",
        headers=owner,
    )
    assert before.status_code == after.status_code == 200
    assert before.json == {"dates": ["2025-12-05", "2026-01-05"]}
    assert after.json == {"dates": ["2026-01-07"]}

    invalid_date = client.get(
        f"/api/backtest/runs/{run_id}/candles?date=2026-02-30",
        headers=owner,
    )
    outside_selection = client.get(
        f"/api/backtest/runs/{run_id}/candles?date=2026-02-08",
        headers=owner,
    )
    assert invalid_date.status_code == 400
    assert outside_selection.status_code == 400

    first_day = client.get(
        f"/api/backtest/runs/{run_id}/candles?date=2026-01-05",
        headers=owner,
    )
    empty_day = client.get(
        f"/api/backtest/runs/{run_id}/candles?date=2026-01-06",
        headers=owner,
    )
    last_day = client.get(
        f"/api/backtest/runs/{run_id}/candles?date=2026-01-07",
        headers=owner,
    )
    assert first_day.status_code == empty_day.status_code == last_day.status_code == 200
    assert [item["time_ms"] for item in first_day.json["candles"]] == sorted(
        item["time_ms"] for item in first_day.json["candles"]
    )
    assert [item["time_ms"] for item in first_day.json["candles"]] == [
        1767571200000,
        1767571260000,
    ]
    assert empty_day.json == {"candles": []}
    assert len(last_day.json["candles"]) == 1
    warmup_day = client.get(
        f"/api/backtest/runs/{run_id}/candles?date=2025-12-05",
        headers=owner,
    )
    assert warmup_day.status_code == 200
    assert len(warmup_day.json["candles"]) == 1
    assert run["snapshot"]["candle_count"] == 4
    assert run["snapshot"]["replay_start_source_index"] == 1
    assert run["replay_cursor"]["source_candle_index"] == 1

    # The snapshot is a fixed artifact; the worker will not fetch refreshed
    # source data for an already ready run.
    snapshot_before = run["snapshot"]
    with app.app_context():
        from app.backtests.worker import BacktestWorker

        assert not BacktestWorker(
            provider=provider, clock=_Clock()
        ).process_one()
    reread = client.get(
        f"/api/backtest/runs/{run_id}", headers=owner
    )
    assert reread.json["run"]["snapshot"] == snapshot_before
    assert provider.calls == [
        ("EUR-USD", date(2025, 12, day)) for day in range(5, 32)
    ] + [("EUR-USD", date(2026, 1, day)) for day in range(1, 8)]

    assert client.get(
        f"/api/backtest/runs/{run_id}/candle-dates", headers=other_user
    ).status_code == 404
    assert client.get(
        f"/api/backtest/runs/{run_id}/candles?date=2026-01-05",
        headers=other_user,
    ).status_code == 404


def test_replay_cursor_accepts_valid_selection_and_intentional_step_back(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "replay-cursor-owner")
    run_id, run, _ = _create_ready_run(app, client, owner)
    first_time = 1767571200000
    last_time = 1767744000000
    warmup_time = int(
        datetime(2025, 12, 5, tzinfo=timezone.utc).timestamp() * 1000
    )

    initial = _cursor_values(run["replay_cursor"])
    assert initial == {
        "source_candle_index": 1,
        "time_ms": first_time,
        "revision": 0,
    }

    warmup_write = client.put(
        f"/api/backtest/runs/{run_id}/replay-position",
        json={
            "source_candle_index": 0,
            "time_ms": warmup_time,
            "expected_revision": 0,
        },
        headers=owner,
    )
    assert warmup_write.status_code == 400

    forward = client.put(
        f"/api/backtest/runs/{run_id}/replay-position",
        json={
            "source_candle_index": 3,
            "time_ms": last_time,
            "expected_revision": 0,
        },
        headers=owner,
    )
    assert forward.status_code == 200
    assert _cursor_values(forward.json["replay_cursor"]) == {
        "source_candle_index": 3,
        "time_ms": last_time,
        "revision": 1,
    }

    step_back = client.put(
        f"/api/backtest/runs/{run_id}/replay-position",
        json={
            "source_candle_index": 1,
            "time_ms": first_time,
            "expected_revision": 1,
        },
        headers=owner,
    )
    assert step_back.status_code == 200
    assert _cursor_values(step_back.json["replay_cursor"]) == {
        "source_candle_index": 1,
        "time_ms": first_time,
        "revision": 2,
    }

    assert _saved_cursor(client, owner, run_id) == {
        "source_candle_index": 1,
        "time_ms": first_time,
        "revision": 2,
    }


def test_stale_revision_mismatched_pair_and_nonowner_writes_do_not_overwrite(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "replay-cursor-writer")
    other_user = _register(client, "replay-cursor-nonowner")
    run_id, run, _ = _create_ready_run(app, client, owner)
    first_time = run["replay_cursor"]["time_ms"]
    final_time = 1767744000000

    moved = client.put(
        f"/api/backtest/runs/{run_id}/replay-position",
        json={
            "source_candle_index": 3,
            "time_ms": final_time,
            "expected_revision": 0,
        },
        headers=owner,
    )
    assert moved.status_code == 200
    assert moved.json["replay_cursor"]["revision"] == 1

    stale = client.put(
        f"/api/backtest/runs/{run_id}/replay-position",
        json={
            "source_candle_index": 2,
            "time_ms": first_time + 60_000,
            "expected_revision": 0,
        },
        headers=owner,
    )
    assert stale.status_code == 409
    assert _saved_cursor(client, owner, run_id) == {
        "source_candle_index": 3,
        "time_ms": final_time,
        "revision": 1,
    }

    mismatch = client.put(
        f"/api/backtest/runs/{run_id}/replay-position",
        json={
            "source_candle_index": 3,
            "time_ms": first_time,
            "expected_revision": 1,
        },
        headers=owner,
    )
    assert mismatch.status_code == 400
    assert _saved_cursor(client, owner, run_id) == {
        "source_candle_index": 3,
        "time_ms": final_time,
        "revision": 1,
    }

    nonowner = client.put(
        f"/api/backtest/runs/{run_id}/replay-position",
        json={
            "source_candle_index": 1,
            "time_ms": first_time,
            "expected_revision": 1,
        },
        headers=other_user,
    )
    assert nonowner.status_code == 404
    assert _saved_cursor(client, owner, run_id) == {
        "source_candle_index": 3,
        "time_ms": final_time,
        "revision": 1,
    }


def test_flat_chart_tab_write_api_is_retired_for_dockable_workspaces(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "replay-tabs-owner")
    run_id, _, _ = _create_ready_run(app, client, owner)

    detail = client.get(f"/api/backtest/runs/{run_id}", headers=owner)
    assert detail.status_code == 200
    assert detail.json["run"]["tabs"] == []

    workspace = client.get(
        f"/api/backtest/runs/{run_id}/chart-workspace", headers=owner
    )
    assert workspace.status_code == 200
    assert workspace.json["workspace"] is None
    assert workspace.json["legacy_tabs"] == []

    retired = client.put(
        f"/api/backtest/runs/{run_id}/chart-tabs",
        json={"tabs": [{"id": "chart-1", "position": 0, "interval_minutes": 1}]},
        headers=owner,
    )
    assert retired.status_code == 404


def test_simulation_routes_accept_exact_limit_touch_and_return_committed_position(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "simulation-route-owner")
    run_id, run, _ = _create_ready_run(app, client, owner)

    initial = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert initial.status_code == 200
    assert initial.json["committed_sequence"] == 0
    assert initial.json["current_balance_usd"] == 10_000
    assert initial.json["current_quote_to_usd_rate"] == 1

    invalid_precision = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "bad-precision",
            "expected_revision": 0,
            "side": "buy",
            "order_type": "limit",
            "auto_size": False,
            "lots": 0.1,
            "entry_price": 1.200001,
            "stop_loss": 1.19,
            "take_profit": 1.21,
        },
        headers=owner,
    )
    assert invalid_precision.status_code == 400

    submitted = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "limit-entry-1",
            "expected_revision": 0,
            "side": "buy",
            "order_type": "limit",
            "auto_size": False,
            "lots": 0.1,
            "entry_price": 1.2,
            "stop_loss": 1.19,
            "take_profit": 1.21,
        },
        headers=owner,
    )
    assert submitted.status_code == 200
    assert submitted.json["state"] == "committed"
    assert submitted.json["result"]["lots"] == 0.1

    advanced = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "advance-through-touch",
            "expected_revision": submitted.json["control_revision"],
            "target_source_index": run["snapshot"]["replay_start_source_index"] + 1,
        },
        headers=owner,
    )
    assert advanced.status_code == 200
    assert advanced.json["state"] == "committed", advanced.json

    state = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert state.status_code == 200
    assert state.json["committed_sequence"] == 2
    assert state.json["backward_navigation_locked"] is True
    assert state.json["current_balance_usd"] == 10_000
    assert len(state.json["fills"]) == 1
    assert state.json["fills"][0]["reference_price"] == 1.2
    assert len(state.json["positions"]) == 1
    assert state.json["positions"][0]["status"] == "open"
    position = state.json["positions"][0]
    initial_risk = position["initial_risk_usd"]
    assert position["unrealized_pnl_usd"] == 5.0

    target_edit = client.put(
        f"/api/backtest/runs/{run_id}/simulation/positions/{position['position_id']}/protection",
        json={
            "client_operation_id": "target-only-edit",
            "expected_revision": 2,
            "take_profit": 1.22,
        },
        headers=owner,
    )
    assert target_edit.status_code == 200
    assert target_edit.json["result"]["tag_ids"] == []
    assert target_edit.json["result"]["stop_moved"] is False
    assert target_edit.json["result"]["initial_risk_usd"] == initial_risk

    stop_edit_request = {
        "client_operation_id": "stop-move-edit",
        "expected_revision": 3,
        "stop_loss": 1.2004,
    }
    stop_edit = client.put(
        f"/api/backtest/runs/{run_id}/simulation/positions/{position['position_id']}/protection",
        json=stop_edit_request,
        headers=owner,
    )
    assert stop_edit.status_code == 200
    assert stop_edit.json["result"]["stop_moved"] is True
    assert stop_edit.json["result"]["stop_loss"] == 1.2004
    assert stop_edit.json["result"]["initial_risk_usd"] == initial_risk
    assert len(stop_edit.json["result"]["tag_ids"]) == 1
    # A same-key retry returns the stored operation without creating another tag.
    assert client.put(
        f"/api/backtest/runs/{run_id}/simulation/positions/{position['position_id']}/protection",
        json=stop_edit_request,
        headers=owner,
    ).json == stop_edit.json

    closed = client.post(
        f"/api/backtest/runs/{run_id}/simulation/positions/{position['position_id']}/close",
        json={
            "client_operation_id": "manual-close-at-current-close",
            "expected_revision": 4,
        },
        headers=owner,
    )
    assert closed.status_code == 200
    assert closed.json["result"]["closed"] is True
    assert closed.json["result"]["current_balance_usd"] == 10_005

    final_state = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert final_state.status_code == 200
    assert final_state.json["current_balance_usd"] == 10_005
    assert final_state.json["positions"] == []
    assert len(final_state.json["closed_trades"]) == 1

    from app.repositories.execution_repo import ExecutionRepository
    from app.repositories.trade_repo import TradeRepository
    from app.extensions import mongo
    from bson import ObjectId

    run_document = mongo.db.backtest_runs.find_one({"_id": ObjectId(run_id)})
    user_id = str(run_document["user_id"])
    trade_repository = TradeRepository()
    published_trades = trade_repository.find_by_user(user_id)
    assert len(published_trades) == 1
    published_trade = published_trades[0]
    assert published_trade["status"] == "closed"
    assert published_trade["initial_risk"] == initial_risk
    assert published_trade["net_pnl"] == 5.0
    assert len(published_trade["tag_ids"]) == 1
    assert len(
        ExecutionRepository().find_by_trade(str(published_trade["_id"]))
    ) == 2
    tag = mongo.db.tags.find_one(
        {"user_id": published_trade["user_id"], "name": "stop-moved"}
    )
    assert tag["_id"] == published_trade["tag_ids"][0]
    assert mongo.db.tag_categories.find_one({"_id": tag["category_id"]})[
        "system_key"
    ] == "general"


def test_short_position_accepts_favorable_stop_below_entry_but_above_close(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "simulation-short-profit-stop-owner")
    run_id, run, _ = _create_ready_run(
        app,
        client,
        owner,
        current_candle_overrides={"close": 1.100505},
        next_candle_overrides={
            "open": 1.099995,
            "high": 1.1001,
            "low": 1.099,
            "close": 1.0995,
        },
    )

    submitted = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "short-profit-stop-entry",
            "expected_revision": 0,
            "side": "sell",
            "order_type": "market",
            "auto_size": False,
            "lots": 0.1,
            "stop_loss": 1.11,
            "take_profit": 1.09,
        },
        headers=owner,
    )
    assert submitted.status_code == 200, submitted.json

    advanced = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "short-profit-stop-advance",
            "expected_revision": submitted.json["control_revision"],
            "target_source_index": run["snapshot"]["replay_start_source_index"] + 1,
        },
        headers=owner,
    )
    assert advanced.status_code == 200, advanced.json
    state = client.get(f"/api/backtest/runs/{run_id}/simulation", headers=owner)
    assert state.status_code == 200
    day_candles = client.get(
        f"/api/backtest/runs/{run_id}/candles?date=2026-01-05", headers=owner
    )
    assert day_candles.status_code == 200
    current_candle = next(
        candle for candle in day_candles.json["candles"]
        if candle["time_ms"] == state.json["cursor"]["time_ms"]
    )
    assert current_candle["close"] == 1.0995
    position = state.json["positions"][0]
    assert position["side"] == "short"
    assert position["weighted_entry_price"] > 1.0996 > 1.0995

    protection = client.put(
        f"/api/backtest/runs/{run_id}/simulation/positions/{position['position_id']}/protection",
        json={
            "client_operation_id": "short-profit-stop-edit",
            "expected_revision": advanced.json["control_revision"],
            "stop_loss": 1.0996,
        },
        headers=owner,
    )
    assert protection.status_code == 200, protection.json
    assert protection.json["result"]["stop_loss"] == 1.0996
    assert protection.json["result"]["stop_moved"] is True

    at_close = client.put(
        f"/api/backtest/runs/{run_id}/simulation/positions/{position['position_id']}/protection",
        json={
            "client_operation_id": "short-profit-stop-at-close",
            "expected_revision": protection.json["control_revision"],
            "stop_loss": 1.0995,
        },
        headers=owner,
    )
    assert at_close.status_code == 200
    assert at_close.json["state"] == "rejected"
    assert "must remain above the current close" in at_close.json["result"]["message"]
    after_rejection = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert after_rejection.json["positions"][0]["stop_loss_price"] == 1.0996

    next_source_index = after_rejection.json["cursor"]["source_candle_index"] + 1
    gap_advance = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "short-profit-stop-next-candle",
            "expected_revision": after_rejection.json["control_revision"],
            "target_source_index": next_source_index,
        },
        headers=owner,
    )
    assert gap_advance.status_code == 200, gap_advance.json
    closed_state = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert closed_state.status_code == 200
    assert closed_state.json["positions"] == []
    stop_fill = next(
        fill for fill in closed_state.json["fills"]
        if fill["entry_exit"] == "Exit"
    )
    assert stop_fill["order_type"] == "stop_market"
    assert stop_fill["source_candle_index"] == next_source_index
    assert stop_fill["reference_price"] == 1.3


def test_market_order_accepts_half_tick_midpoint_close_and_next_open(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "simulation-half-tick-owner")
    run_id, run, _ = _create_ready_run(
        app,
        client,
        owner,
        current_candle_overrides={"close": 1.100505},
        next_candle_overrides={"open": 1.200005, "close": 1.200505},
    )

    submitted = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "half-tick-market-entry",
            "expected_revision": 0,
            "side": "buy",
            "order_type": "market",
            "auto_size": False,
            "lots": 0.1,
            "stop_loss": 1.09,
            "take_profit": 1.11,
        },
        headers=owner,
    )
    assert submitted.status_code == 200, submitted.json

    working = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert working.status_code == 200
    assert working.json["orders"][0]["sizing_reference_entry_price"] == 1.10051

    advanced = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "half-tick-market-advance",
            "expected_revision": submitted.json["control_revision"],
            "target_source_index": run["snapshot"]["replay_start_source_index"] + 1,
        },
        headers=owner,
    )
    assert advanced.status_code == 200, advanced.json
    assert advanced.json["state"] == "committed"

    state = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert state.status_code == 200
    assert state.json["fills"][0]["reference_price"] == 1.20001
    assert state.json["fills"][0]["fill_price"] == 1.20001
    assert state.json["positions"][0]["unrealized_pnl_usd"] is not None

    position_id = state.json["positions"][0]["position_id"]
    protection = client.put(
        f"/api/backtest/runs/{run_id}/simulation/positions/{position_id}/protection",
        json={
            "client_operation_id": "half-tick-protection-edit",
            "expected_revision": advanced.json["control_revision"],
            "take_profit": 1.21,
        },
        headers=owner,
    )
    assert protection.status_code == 200, protection.json

    closed = client.post(
        f"/api/backtest/runs/{run_id}/simulation/positions/{position_id}/close",
        json={
            "client_operation_id": "half-tick-manual-close",
            "expected_revision": protection.json["control_revision"],
        },
        headers=owner,
    )
    assert closed.status_code == 200, closed.json
