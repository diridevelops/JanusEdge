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


def _create_ready_run(app, client, headers):
    from app.backtests.worker import BacktestWorker

    response = client.post(
        "/api/backtest/runs",
        json={
            "instrument": "EUR-USD",
            "start_date": "2026-01-05",
            "end_date": "2026-01-07",
            "display_timezone": "UTC",
        },
        headers=headers,
    )
    assert response.status_code == 202
    run_id = response.json["run"]["id"]

    jan_5 = date(2026, 1, 5)
    jan_6 = date(2026, 1, 6)
    jan_7 = date(2026, 1, 7)
    dec_5 = date(2025, 12, 5)
    provider = _Provider(
        {
            dec_5: _day_result(dec_5, [_candle(dec_5, 0, 0.9)]),
            jan_5: _day_result(
                jan_5,
                [_candle(jan_5, 0, 1.1), _candle(jan_5, 1, 1.2)],
            ),
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
