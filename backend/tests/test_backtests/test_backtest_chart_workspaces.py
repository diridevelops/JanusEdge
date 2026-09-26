"""Authenticated dockable chart-workspace API contract tests."""

from datetime import date, datetime, timezone
from copy import deepcopy

from bson import ObjectId


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


def _candle(utc_date):
    time_ms = int(
        datetime(
            utc_date.year,
            utc_date.month,
            utc_date.day,
            tzinfo=timezone.utc,
        ).timestamp()
        * 1000
    )
    return {
        "time_ms": time_ms,
        "open": 1.1,
        "high": 1.101,
        "low": 1.099,
        "close": 1.1005,
        "volume": 30,
    }


class _Provider:
    def fetch_day(self, instrument, utc_date):
        assert instrument == "EUR-USD"
        assert utc_date == date(2026, 1, 5)
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
    from app.extensions import mongo

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
        worker = BacktestWorker(provider=_Provider(), clock=_Clock())
        assert worker.process_one()
        # This helper intentionally avoids GET /runs/{id}, which used to
        # materialize a default legacy flat tab as a side effect.
        mongo.db.backtest_chart_tabs.delete_many(
            {"run_id": ObjectId(run_id)}
        )
    return run_id


def _workspace(run_id, panels=None):
    panel_specs = panels or [{"id": "chart-1", "interval_minutes": 1}]
    tabs = []
    panel_map = {}
    for spec in panel_specs:
        panel_id = spec["id"]
        interval = spec["interval_minutes"]
        title = spec.get("title", panel_id)
        panel_map[panel_id] = {
            "id": panel_id,
            "type": "backtest-chart",
            "interval_minutes": interval,
        }
        tabs.append(
            {
                "type": "tab",
                "id": panel_id,
                "name": title,
                "component": "backtest-chart",
                "config": {
                    "id": panel_id,
                    "kind": "backtest-chart",
                    "title": title,
                    "config": {"interval_minutes": interval},
                },
            }
        )

    return {
        "schema_version": 1,
        "layout_engine": "flexlayout-react",
        "id": run_id,
        "name": "default",
        "tree": {
            "global": {"tabEnableClose": True},
            "borders": [],
            "layout": {
                "type": "row",
                "id": "root-row",
                "weight": 100,
                "children": [
                    {
                        "type": "tabset",
                        "id": "tabset-1",
                        "weight": 100,
                        "selected": 0,
                        "children": tabs,
                    }
                ],
            },
        },
        "panels": panel_map,
    }


def _save(client, headers, run_id, workspace, expected_revision=0):
    return client.put(
        f"/api/backtest/runs/{run_id}/chart-workspace",
        json={
            "expected_revision": expected_revision,
            "workspace": workspace,
        },
        headers=headers,
    )


def test_workspace_is_owner_scoped_and_uses_revisioned_single_document(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "workspace-owner")
    other_user = _register(client, "workspace-other-user")
    owner_run = _create_ready_run(app, client, owner)
    other_run = _create_ready_run(app, client, other_user)

    empty = client.get(
        f"/api/backtest/runs/{owner_run}/chart-workspace", headers=owner
    )
    assert empty.status_code == 200
    assert empty.json["workspace"] is None
    assert empty.json["revision"] == 0
    assert empty.json["legacy_tabs"] == []

    saved = _save(client, owner, owner_run, _workspace(owner_run))
    assert saved.status_code == 200
    assert saved.json["revision"] == 1
    assert saved.json["workspace"]["id"] == owner_run
    assert saved.json["workspace"]["panels"] == {
        "chart-1": {
            "id": "chart-1",
            "type": "backtest-chart",
            "interval_minutes": 1,
        }
    }

    restored = client.get(
        f"/api/backtest/runs/{owner_run}/chart-workspace", headers=owner
    )
    assert restored.status_code == 200
    assert restored.json["workspace"] == saved.json["workspace"]

    hidden_read = client.get(
        f"/api/backtest/runs/{other_run}/chart-workspace", headers=owner
    )
    hidden_write = _save(
        client, owner, other_run, _workspace(other_run)
    )
    assert hidden_read.status_code == 404
    assert hidden_write.status_code == 404


def test_legacy_tabs_are_read_in_position_order_without_mutation(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "workspace-legacy")
    run_id = _create_ready_run(app, client, owner)
    from app.extensions import mongo

    with app.app_context():
        user_id = client.get("/api/auth/me", headers=owner).json["id"]
        mongo.db.backtest_chart_tabs.insert_many(
            [
                {
                    "user_id": ObjectId(user_id),
                    "run_id": ObjectId(run_id),
                    "id": "chart-later",
                    "position": 1,
                    "interval_minutes": 15,
                },
                {
                    "user_id": ObjectId(user_id),
                    "run_id": ObjectId(run_id),
                    "id": "chart-earlier",
                    "position": 0,
                    "interval_minutes": 5,
                },
            ]
        )

    legacy = client.get(
        f"/api/backtest/runs/{run_id}/chart-workspace", headers=owner
    )
    assert legacy.status_code == 200
    assert legacy.json["workspace"] is None
    assert legacy.json["legacy_tabs"] == [
        {"id": "chart-earlier", "position": 0, "interval_minutes": 5},
        {"id": "chart-later", "position": 1, "interval_minutes": 15},
    ]
    assert mongo.db.backtest_chart_workspaces.count_documents({}) == 0

    migrated = _save(
        client,
        owner,
        run_id,
        _workspace(
            run_id,
            [
                {"id": "chart-earlier", "interval_minutes": 5},
                {"id": "chart-later", "interval_minutes": 15},
            ],
        ),
    )
    assert migrated.status_code == 200
    assert migrated.json["revision"] == 1
    assert mongo.db.backtest_chart_tabs.count_documents({}) == 0


def test_workspace_rejects_invalid_schema_types_intervals_and_empty_layout(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "workspace-validation")
    run_id = _create_ready_run(app, client, owner)
    base = _workspace(run_id)

    invalid_workspaces = []
    wrong_version = deepcopy(base)
    wrong_version["schema_version"] = True
    invalid_workspaces.append(wrong_version)

    wrong_id = deepcopy(base)
    wrong_id["id"] = "another-run"
    invalid_workspaces.append(wrong_id)

    for interval in (True, 0, 1441, 1.5, "5"):
        invalid_interval = deepcopy(base)
        invalid_interval["panels"]["chart-1"]["interval_minutes"] = interval
        invalid_interval["tree"]["layout"]["children"][0]["children"][0]["config"]["config"]["interval_minutes"] = interval
        invalid_workspaces.append(invalid_interval)

    empty_layout = deepcopy(base)
    empty_layout["panels"] = {}
    empty_layout["tree"]["layout"]["children"] = []
    invalid_workspaces.append(empty_layout)

    mismatch = deepcopy(base)
    mismatch["panels"]["orphan-chart"] = {
        "id": "orphan-chart",
        "type": "backtest-chart",
        "interval_minutes": 1,
    }
    invalid_workspaces.append(mismatch)

    duplicate_id = deepcopy(base)
    duplicate_id["tree"]["layout"]["children"][0]["children"].append(
        deepcopy(duplicate_id["tree"]["layout"]["children"][0]["children"][0])
    )
    invalid_workspaces.append(duplicate_id)

    unsupported_component = deepcopy(base)
    unsupported_component["tree"]["layout"]["children"][0]["children"][0]["component"] = "watchlist"
    invalid_workspaces.append(unsupported_component)

    for workspace in invalid_workspaces:
        rejected = _save(client, owner, run_id, workspace)
        assert rejected.status_code == 400, rejected.json

    assert client.get(
        f"/api/backtest/runs/{run_id}/chart-workspace", headers=owner
    ).json["workspace"] is None


def test_stale_workspace_revision_returns_conflict_without_overwriting(
    app, client, monkeypatch
):
    _patch_catalog(monkeypatch)
    owner = _register(client, "workspace-conflict")
    run_id = _create_ready_run(app, client, owner)
    initial = _workspace(run_id)
    first = _save(client, owner, run_id, initial, expected_revision=0)
    assert first.status_code == 200
    assert first.json["revision"] == 1

    stale = _workspace(
        run_id, [{"id": "chart-1", "interval_minutes": 5}]
    )
    conflict = _save(client, owner, run_id, stale, expected_revision=0)
    assert conflict.status_code == 409
    assert conflict.json["error"]["details"] == [{"current_revision": 1}]

    restored = client.get(
        f"/api/backtest/runs/{run_id}/chart-workspace", headers=owner
    )
    assert restored.json["revision"] == 1
    assert restored.json["workspace"]["panels"]["chart-1"]["interval_minutes"] == 1
