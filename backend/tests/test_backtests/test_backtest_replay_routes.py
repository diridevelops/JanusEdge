"""Owner-scoped immutable snapshot and replay cursor API tests."""

from datetime import date, datetime, timezone

import pytest


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
    following_candle_overrides=None,
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
    jan_5_candles = [current_candle, next_candle]
    if following_candle_overrides is not None:
        following_candle = _candle(jan_5, 2, 1.3)
        following_candle.update(following_candle_overrides)
        jan_5_candles.append(following_candle)
    provider = _Provider(
        {
            dec_5: _day_result(dec_5, [_candle(dec_5, 0, 0.9)]),
            jan_5: _day_result(jan_5, jan_5_candles),
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
    assert forward.json["replay_cursor"]["furthest_source_candle_index"] == 3
    assert forward.json["replay_cursor"]["furthest_time_ms"] == last_time

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
    assert step_back.json["replay_cursor"]["furthest_source_candle_index"] == 3
    assert step_back.json["replay_cursor"]["furthest_time_ms"] == last_time

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
    assert state.json["backward_navigation_locked"] is False
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


def test_same_side_entry_scales_into_one_position_and_trade_with_average_entry(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "simulation-scale-in-owner")
    run_id, run, _ = _create_ready_run(
        app,
        client,
        owner,
        following_candle_overrides={},
    )
    replay_start = run["snapshot"]["replay_start_source_index"]

    first_entry = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "scale-in-first-entry",
            "expected_revision": 0,
            "side": "buy",
            "order_type": "market",
            "auto_size": False,
            "lots": 0.1,
            "stop_loss": 1.0,
            "take_profit": 1.5,
        },
        headers=owner,
    )
    assert first_entry.status_code == 200, first_entry.json
    first_advance = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "scale-in-first-fill",
            "expected_revision": first_entry.json["control_revision"],
            "target_source_index": replay_start + 1,
        },
        headers=owner,
    )
    assert first_advance.status_code == 200, first_advance.json

    second_entry = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "scale-in-second-entry",
            "expected_revision": first_advance.json["control_revision"],
            "side": "buy",
            "order_type": "market",
            "auto_size": False,
            "lots": 0.2,
            # These bracket levels belong to this order only if the first
            # position is no longer open when the market order fills.
            "stop_loss": 1.19,
            "take_profit": 1.4,
        },
        headers=owner,
    )
    assert second_entry.status_code == 200, second_entry.json
    second_advance = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "scale-in-second-fill",
            "expected_revision": second_entry.json["control_revision"],
            "target_source_index": replay_start + 2,
        },
        headers=owner,
    )
    assert second_advance.status_code == 200, second_advance.json

    state_response = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert state_response.status_code == 200
    state = state_response.json
    assert len(state["positions"]) == 1
    position = state["positions"][0]
    assert position["remaining_lots"] == 0.3
    assert position["weighted_entry_price"] == pytest.approx(
        (1.2 * 0.1 + 1.3 * 0.2) / 0.3
    )
    assert position["stop_loss_price"] == 1.0
    assert position["take_profit_price"] == 1.5
    assert position["initial_risk_usd"] == pytest.approx(8_000)
    entry_fills = [fill for fill in state["fills"] if fill["entry_exit"] == "Entry"]
    assert len(entry_fills) == 2
    assert {fill["simulated_position_id"] for fill in entry_fills} == {
        position["position_id"]
    }
    assert [fill["lots"] for fill in entry_fills] == [0.1, 0.2]
    assert entry_fills[0]["trade_id"] == entry_fills[1]["trade_id"]

    protection_orders = [
        order
        for order in state["orders"]
        if order["role"] in {"protective_stop", "protective_target"}
    ]
    assert len(protection_orders) == 2
    assert {order["lots"] for order in protection_orders} == {0.3}
    assert {
        order["stop_loss_price"]
        for order in protection_orders
        if order["role"] == "protective_stop"
    } == {1.0}
    assert {
        order["take_profit_price"]
        for order in protection_orders
        if order["role"] == "protective_target"
    } == {1.5}

    closed = client.post(
        f"/api/backtest/runs/{run_id}/simulation/positions/{position['position_id']}/close",
        json={
            "client_operation_id": "close-scaled-position",
            "expected_revision": second_advance.json["control_revision"],
        },
        headers=owner,
    )
    assert closed.status_code == 200, closed.json
    assert closed.json.get("result", {}).get("closed") is True, closed.json
    from app.extensions import mongo
    from bson import ObjectId

    trade_doc = mongo.db.trades.find_one(
        {
            "backtest_run_id": ObjectId(run_id),
            "simulated_position_id": ObjectId(position["position_id"]),
            "status": "closed",
        }
    )
    assert trade_doc is not None
    trade_id = str(trade_doc["_id"])
    mode = client.put(
        "/api/workspace/mode",
        json={"active_mode": "backtest"},
        headers=owner,
    )
    assert mode.status_code == 200, mode.json
    details = client.get(f"/api/trades/{trade_id}", headers=owner)
    assert details.status_code == 200, details.json
    trade = details.json["trade"]
    assert trade["avg_entry_price"] == pytest.approx(
        (1.2 * 0.1 + 1.3 * 0.2) / 0.3
    )
    assert trade["total_quantity"] == pytest.approx(0.3)
    assert len(details.json["executions"]) == 3
    assert [execution["entry_exit"] for execution in details.json["executions"]] == [
        "Entry",
        "Entry",
        "Exit",
    ]


def test_scale_in_after_partial_scale_out_updates_open_exposure_and_protection(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "simulation-scale-out-in-owner")
    run_id, run, _ = _create_ready_run(app, client, owner)
    replay_start = run["snapshot"]["replay_start_source_index"]

    initial = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "scale-out-in-initial",
            "expected_revision": 0,
            "side": "buy",
            "order_type": "market",
            "auto_size": False,
            "lots": 0.2,
            "stop_loss": 1.0,
            "take_profit": 1.5,
        },
        headers=owner,
    )
    assert initial.status_code == 200, initial.json
    initial_advance = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "scale-out-in-initial-fill",
            "expected_revision": initial.json["control_revision"],
            "target_source_index": replay_start + 1,
        },
        headers=owner,
    )
    assert initial_advance.status_code == 200, initial_advance.json

    scale_out = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "scale-out-in-partial-exit",
            "expected_revision": initial_advance.json["control_revision"],
            "side": "sell",
            "order_type": "market",
            "auto_size": False,
            "lots": 0.1,
            "stop_loss": 1.5,
            "take_profit": 1.0,
        },
        headers=owner,
    )
    assert scale_out.status_code == 200, scale_out.json
    scale_in = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "scale-out-in-additional-entry",
            "expected_revision": scale_out.json["control_revision"],
            "side": "buy",
            "order_type": "market",
            "auto_size": False,
            "lots": 0.1,
            "stop_loss": 1.19,
            "take_profit": 1.4,
        },
        headers=owner,
    )
    assert scale_in.status_code == 200, scale_in.json
    advanced = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "scale-out-in-process-orders",
            "expected_revision": scale_in.json["control_revision"],
            "target_source_index": replay_start + 2,
        },
        headers=owner,
    )
    assert advanced.status_code == 200, advanced.json

    state_response = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    )
    assert state_response.status_code == 200
    state = state_response.json
    assert len(state["positions"]) == 1
    position = state["positions"][0]
    assert position["remaining_lots"] == pytest.approx(0.2)
    assert position["weighted_entry_price"] == pytest.approx(
        (1.2 * 0.2 + 1.3 * 0.1) / 0.3
    )
    assert position["stop_loss_price"] == 1.0
    assert position["take_profit_price"] == 1.5
    assert len([fill for fill in state["fills"] if fill["entry_exit"] == "Entry"]) == 2
    assert len([fill for fill in state["fills"] if fill["entry_exit"] == "Exit"]) == 1
    protection_orders = [
        order
        for order in state["orders"]
        if order["role"] in {"protective_stop", "protective_target"}
    ]
    assert len(protection_orders) == 2
    assert {order["lots"] for order in protection_orders} == {0.2}


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


def test_rewind_preserves_simulation_state_rejects_stale_entries_and_returns_to_latest(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "simulation-rewind-owner")
    run_id, run, _ = _create_ready_run(app, client, owner)
    replay_start = run["snapshot"]["replay_start_source_index"]
    first_cursor = run["replay_cursor"]

    submitted = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "rewind-limit-order",
            "expected_revision": 0,
            "side": "buy",
            "order_type": "limit",
            "auto_size": False,
            "lots": 0.1,
            "entry_price": 1.2,
            "stop_loss": 1.1995,
            "take_profit": 1.2005,
        },
        headers=owner,
    )
    assert submitted.status_code == 200, submitted.json

    filled = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "rewind-fill-order",
            "expected_revision": submitted.json["control_revision"],
            "target_source_index": replay_start + 1,
        },
        headers=owner,
    )
    assert filled.status_code == 200, filled.json
    state_at_latest = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    ).json

    def open_position_state(state):
        return [
            (position["position_id"], position["status"], position["remaining_lots"])
            for position in state["positions"]
        ]

    def order_state(state):
        return sorted(
            (order["order_id"], order["status"])
            for order in state["orders"]
        )

    assert len(state_at_latest["fills"]) == 1
    assert len(state_at_latest["positions"]) == 1
    committed_balance = state_at_latest["current_balance_usd"]

    rewound = client.post(
        f"/api/backtest/runs/{run_id}/simulation/rewind",
        json={
            "client_operation_id": "rewind-before-new-entry",
            "expected_revision": filled.json["control_revision"],
            "source_candle_index": replay_start,
            "time_ms": first_cursor["time_ms"],
        },
        headers=owner,
    )
    assert rewound.status_code == 200, rewound.json
    state_behind = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    ).json
    assert state_behind["cursor"]["source_candle_index"] == replay_start
    assert state_behind["cursor"]["furthest_source_candle_index"] == replay_start + 1
    assert state_behind["cursor"]["furthest_time_ms"] == state_at_latest["cursor"]["time_ms"]
    assert state_behind["current_balance_usd"] == committed_balance
    assert state_behind["orders"] == state_at_latest["orders"]
    assert state_behind["fills"] == state_at_latest["fills"]
    assert open_position_state(state_behind) == open_position_state(state_at_latest)
    assert state_behind["positions"][0]["unrealized_pnl_usd"] == (
        state_at_latest["positions"][0]["unrealized_pnl_usd"]
    )
    assert state_behind["current_quote_to_usd_rate"] == (
        state_at_latest["current_quote_to_usd_rate"]
    )
    assert state_behind["mark_price"] == state_at_latest["mark_price"]

    stale_entry = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "blocked-while-rewound",
            "expected_revision": rewound.json["control_revision"],
            "side": "buy",
            "order_type": "market",
            "auto_size": False,
            "lots": 0.1,
            "stop_loss": 1.09,
            "take_profit": 1.11,
        },
        headers=owner,
    )
    assert stale_entry.status_code == 200, stale_entry.json
    assert stale_entry.json["state"] == "rejected"
    assert stale_entry.json["result"]["message"] == (
        "Return to the last viewed candle before placing a new order."
    )

    returned = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "return-to-saved-latest",
            "expected_revision": stale_entry.json["control_revision"],
            "target_source_index": replay_start + 1,
        },
        headers=owner,
    )
    assert returned.status_code == 200, returned.json
    state_returned = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    ).json
    assert order_state(state_returned) == order_state(state_at_latest)
    assert state_returned["fills"] == state_at_latest["fills"]
    assert open_position_state(state_returned) == open_position_state(state_at_latest)
    assert state_returned["current_balance_usd"] == committed_balance

    run_detail = client.get(f"/api/backtest/runs/{run_id}", headers=owner).json["run"]
    final_index = run_detail["snapshot"]["candle_count"] - 1
    completed = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "complete-before-rewind",
            "expected_revision": returned.json["control_revision"],
            "target_source_index": final_index,
        },
        headers=owner,
    )
    assert completed.status_code == 200, completed.json
    completed_state = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    ).json
    assert completed_state["status"] == "complete"

    rewound_complete = client.post(
        f"/api/backtest/runs/{run_id}/simulation/rewind",
        json={
            "client_operation_id": "rewind-completed-run",
            "expected_revision": completed.json["control_revision"],
            "source_candle_index": replay_start,
            "time_ms": first_cursor["time_ms"],
        },
        headers=owner,
    )
    assert rewound_complete.status_code == 200, rewound_complete.json
    behind_complete = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    ).json
    assert behind_complete["status"] == "ready"
    assert behind_complete["cursor"]["furthest_source_candle_index"] == final_index
    assert behind_complete["current_balance_usd"] == completed_state["current_balance_usd"]
    assert order_state(behind_complete) == order_state(completed_state)
    assert behind_complete["fills"] == completed_state["fills"]
    assert open_position_state(behind_complete) == open_position_state(completed_state)

    completed_again = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "return-to-final-candle",
            "expected_revision": rewound_complete.json["control_revision"],
            "target_source_index": final_index,
        },
        headers=owner,
    )
    assert completed_again.status_code == 200, completed_again.json
    final_state = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    ).json
    assert final_state["status"] == "complete"
    assert final_state["current_balance_usd"] == completed_state["current_balance_usd"]
    assert order_state(final_state) == order_state(completed_state)
    assert final_state["fills"] == completed_state["fills"]
    assert open_position_state(final_state) == open_position_state(completed_state)


def test_pending_order_remains_working_and_obeys_eligibility_after_rewind(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "simulation-rewind-eligibility-owner")
    run_id, run, _ = _create_ready_run(app, client, owner)
    replay_start = run["snapshot"]["replay_start_source_index"]
    first_cursor = run["replay_cursor"]

    moved = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "eligibility-position-before-order",
            "expected_revision": 0,
            "target_source_index": replay_start + 1,
        },
        headers=owner,
    )
    assert moved.status_code == 200, moved.json

    submitted = client.post(
        f"/api/backtest/runs/{run_id}/simulation/orders",
        json={
            "client_operation_id": "eligible-short-limit",
            "expected_revision": moved.json["control_revision"],
            "side": "sell",
            "order_type": "limit",
            "auto_size": False,
            "lots": 0.1,
            "entry_price": 1.3,
            "stop_loss": 1.31,
            "take_profit": 1.29,
        },
        headers=owner,
    )
    assert submitted.status_code == 200, submitted.json
    assert submitted.json["result"]["eligible_source_index"] == replay_start + 2

    rewound = client.post(
        f"/api/backtest/runs/{run_id}/simulation/rewind",
        json={
            "client_operation_id": "rewind-before-order-eligibility",
            "expected_revision": submitted.json["control_revision"],
            "source_candle_index": replay_start,
            "time_ms": first_cursor["time_ms"],
        },
        headers=owner,
    )
    assert rewound.status_code == 200, rewound.json

    replayed_before_eligibility = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "advance-pre-eligibility-candle",
            "expected_revision": rewound.json["control_revision"],
            "target_source_index": replay_start + 1,
        },
        headers=owner,
    )
    assert replayed_before_eligibility.status_code == 200, replayed_before_eligibility.json
    state_before_eligibility = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    ).json
    assert len(state_before_eligibility["orders"]) == 1
    assert state_before_eligibility["orders"][0]["status"] == "pending"
    assert state_before_eligibility["fills"] == []

    replayed_at_eligibility = client.post(
        f"/api/backtest/runs/{run_id}/simulation/advance",
        json={
            "client_operation_id": "advance-eligible-candle",
            "expected_revision": replayed_before_eligibility.json["control_revision"],
            "target_source_index": replay_start + 2,
        },
        headers=owner,
    )
    assert replayed_at_eligibility.status_code == 200, replayed_at_eligibility.json
    state_at_eligibility = client.get(
        f"/api/backtest/runs/{run_id}/simulation", headers=owner
    ).json
    assert state_at_eligibility["orders"][0]["status"] == "filled", state_at_eligibility
    assert len(state_at_eligibility["fills"]) == 1
    assert state_at_eligibility["fills"][0]["source_candle_index"] == replay_start + 2
    position = state_at_eligibility["positions"][0]
    protection_ids = {
        str(position["stop_loss_order_id"]),
        str(position["take_profit_order_id"]),
    }
    protection_orders = [
        order
        for order in state_at_eligibility["orders"]
        if str(order["order_id"]) in protection_ids
    ]
    assert len(protection_orders) == 2
    assert all(
        order["eligible_source_index"] == replay_start + 3
        for order in protection_orders
    )
