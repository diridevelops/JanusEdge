"""Authenticated run- and interval-scoped drawing API tests."""

from datetime import date, datetime, timezone
import json

MAX_DRAWING_STATE_BYTES = 1_048_576


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


def _candle(utc_date, minute=0):
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
        "open": 1.1,
        "high": 1.101,
        "low": 1.099,
        "close": 1.1005,
        "volume": 30,
    }


class _Provider:
    def __init__(self, utc_date):
        self.utc_date = utc_date

    def fetch_day(self, instrument, utc_date):
        assert instrument == "EUR-USD"
        if utc_date != self.utc_date:
            return {
                "utc_date": utc_date,
                "outcome": "empty",
                "candles": [],
            }
        return {
            "utc_date": utc_date,
            "outcome": "data",
            "candles": [_candle(utc_date)],
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
            "end_date": "2026-01-05",
            "display_timezone": "UTC",
        },
        headers=headers,
    )
    assert response.status_code == 202
    run_id = response.json["run"]["id"]

    with app.app_context():
        worker = BacktestWorker(
            provider=_Provider(date(2026, 1, 5)),
            clock=_Clock(),
        )
        assert worker.process_one()

    ready = client.get(f"/api/backtest/runs/{run_id}", headers=headers)
    assert ready.status_code == 200
    assert ready.json["run"]["status"] == "ready"
    return run_id


def _drawing_state(marker):
    return json.dumps({"saved_marker": marker})


def _save(client, headers, run_id, interval, state, expected_revision=0):
    return client.put(
        f"/api/backtest/runs/{run_id}/drawings?interval_minutes={interval}",
        json={
            "candlekit_version": "0.1.0",
            "schema_version": 1,
            "expected_revision": expected_revision,
            "serialized_state": state,
        },
        headers=headers,
    )


def test_drawing_state_is_scoped_to_owner_run_and_interval(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "drawings-owner")
    other_user = _register(client, "drawings-other-user")
    owner_run = _create_ready_run(app, client, owner)
    owner_other_run = _create_ready_run(app, client, owner)
    other_run = _create_ready_run(app, client, other_user)

    unsaved = client.get(
        f"/api/backtest/runs/{owner_run}/drawings?interval_minutes=5",
        headers=owner,
    )
    assert unsaved.status_code == 200
    assert unsaved.json["interval_minutes"] == 5
    assert unsaved.json["serialized_state"] is None
    assert unsaved.json["revision"] == 0

    five_minute_state = _drawing_state("owner-run-five-minute")
    fifteen_minute_state = _drawing_state("owner-run-fifteen-minute")
    five_minute_saved = _save(
        client, owner, owner_run, 5, five_minute_state
    )
    fifteen_minute_saved = _save(
        client, owner, owner_run, 15, fifteen_minute_state
    )
    assert five_minute_saved.status_code == 200
    assert fifteen_minute_saved.status_code == 200
    assert five_minute_saved.json["revision"] == 1
    assert fifteen_minute_saved.json["revision"] == 1

    five_minute_loaded = client.get(
        f"/api/backtest/runs/{owner_run}/drawings?interval_minutes=5",
        headers=owner,
    )
    fifteen_minute_loaded = client.get(
        f"/api/backtest/runs/{owner_run}/drawings?interval_minutes=15",
        headers=owner,
    )
    assert five_minute_loaded.json["serialized_state"] == five_minute_state
    assert fifteen_minute_loaded.json["serialized_state"] == fifteen_minute_state

    # The run is part of the storage key, even for the same owner and interval.
    another_run_empty = client.get(
        f"/api/backtest/runs/{owner_other_run}/drawings?interval_minutes=5",
        headers=owner,
    )
    assert another_run_empty.status_code == 200
    assert another_run_empty.json["serialized_state"] is None
    assert another_run_empty.json["revision"] == 0

    # Both reads and writes hide another user's run as not found.
    hidden_read = client.get(
        f"/api/backtest/runs/{other_run}/drawings?interval_minutes=5",
        headers=owner,
    )
    hidden_write = _save(
        client, owner, other_run, 5, _drawing_state("cross-owner")
    )
    assert hidden_read.status_code == 404
    assert hidden_write.status_code == 404

    # A second authenticated user cannot read or overwrite the owner's state.
    other_read = client.get(
        f"/api/backtest/runs/{owner_run}/drawings?interval_minutes=5",
        headers=other_user,
    )
    other_write = _save(
        client, other_user, owner_run, 5, _drawing_state("other-user")
    )
    assert other_read.status_code == 404
    assert other_write.status_code == 404
    unchanged = client.get(
        f"/api/backtest/runs/{owner_run}/drawings?interval_minutes=5",
        headers=owner,
    )
    assert unchanged.json["serialized_state"] == five_minute_state
    assert unchanged.json["revision"] == 1


def test_empty_drawing_state_is_a_valid_saved_payload(app, client, monkeypatch):
    _patch_catalog(monkeypatch)
    owner = _register(client, "drawings-empty-state")
    run_id = _create_ready_run(app, client, owner)

    saved = _save(client, owner, run_id, 1, "{}")
    assert saved.status_code == 200
    assert saved.json["interval_minutes"] == 1
    assert saved.json["candlekit_version"] == "0.1.0"
    assert saved.json["schema_version"] == 1
    assert saved.json["revision"] == 1
    assert saved.json["serialized_state"] == "{}"

    # CandleKit DrawingEngine.export() serializes its drawings array directly.
    array_saved = _save(
        client,
        owner,
        run_id,
        1,
        "[]",
        expected_revision=1,
    )
    assert array_saved.status_code == 200
    assert array_saved.json["revision"] == 2
    assert array_saved.json["serialized_state"] == "[]"

    restored = client.get(
        f"/api/backtest/runs/{run_id}/drawings?interval_minutes=1",
        headers=owner,
    )
    assert restored.status_code == 200
    assert restored.json["serialized_state"] == "[]"
    assert restored.json["revision"] == 2


def test_drawing_interval_and_payload_validation_preserve_saved_state(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "drawings-payload-validation")
    run_id = _create_ready_run(app, client, owner)
    original_state = _drawing_state("last-valid")
    initial = _save(client, owner, run_id, 5, original_state)
    assert initial.status_code == 200
    assert initial.json["revision"] == 1

    oversized_state = json.dumps(
        {"payload": "x" * MAX_DRAWING_STATE_BYTES}
    )
    assert len(oversized_state.encode("utf-8")) > MAX_DRAWING_STATE_BYTES

    for invalid_interval in ("0", "1441", "1.5", "not-an-integer"):
        read = client.get(
            f"/api/backtest/runs/{run_id}/drawings"
            f"?interval_minutes={invalid_interval}",
            headers=owner,
        )
        write = _save(
            client,
            owner,
            run_id,
            invalid_interval,
            _drawing_state("invalid-interval"),
            expected_revision=1,
        )
        assert read.status_code == 400
        assert write.status_code == 400

    invalid_payloads = [
        {
            "candlekit_version": "0.1.0",
            "schema_version": 1,
            "expected_revision": 1,
            "serialized_state": "not valid JSON",
        },
        {
            "candlekit_version": "0.1.0",
            "schema_version": 1,
            "expected_revision": 1,
            "serialized_state": {"drawings": []},
        },
        {
            "candlekit_version": "0.1.0",
            "schema_version": 1,
            "expected_revision": 1,
        },
        {
            "candlekit_version": "",
            "schema_version": 1,
            "expected_revision": 1,
            "serialized_state": "{}",
        },
        {
            "candlekit_version": "0.1.0",
            "schema_version": True,
            "expected_revision": 1,
            "serialized_state": "{}",
        },
        {
            "candlekit_version": "0.1.0",
            "schema_version": 1,
            "expected_revision": -1,
            "serialized_state": "{}",
        },
        {
            "candlekit_version": "0.1.0",
            "schema_version": 1,
            "expected_revision": 1,
            "serialized_state": oversized_state,
        },
    ]
    for payload in invalid_payloads:
        rejected = client.put(
            f"/api/backtest/runs/{run_id}/drawings?interval_minutes=5",
            json=payload,
            headers=owner,
        )
        assert rejected.status_code == 400

    unchanged = client.get(
        f"/api/backtest/runs/{run_id}/drawings?interval_minutes=5",
        headers=owner,
    )
    assert unchanged.status_code == 200
    assert unchanged.json["serialized_state"] == original_state
    assert unchanged.json["revision"] == 1


def test_stale_drawing_revision_returns_conflict_without_overwriting(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "drawings-revision-conflict")
    run_id = _create_ready_run(app, client, owner)
    latest_state = _drawing_state("revision-one")

    first_save = _save(client, owner, run_id, 60, latest_state)
    assert first_save.status_code == 200
    assert first_save.json["revision"] == 1

    stale_write = _save(
        client,
        owner,
        run_id,
        60,
        _drawing_state("stale-overwrite"),
        expected_revision=0,
    )
    assert stale_write.status_code == 409

    restored = client.get(
        f"/api/backtest/runs/{run_id}/drawings?interval_minutes=60",
        headers=owner,
    )
    assert restored.status_code == 200
    assert restored.json["serialized_state"] == latest_state
    assert restored.json["revision"] == 1
