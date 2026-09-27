"""Permanent Backtest run deletion and cleanup recovery tests."""

from datetime import datetime, timedelta, timezone
from io import BytesIO

from bson import ObjectId

from app.extensions import mongo


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


def _create_run(client, headers, monkeypatch):
    import app.backtests.service as service_module

    monkeypatch.setattr(
        service_module,
        "fetch_instrument_codes",
        lambda: ["EUR-USD"],
    )
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
    return response.json["run"]


class _Clock:
    def __init__(self):
        self.now = datetime(2026, 12, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def _put_object(client, bucket, object_name, payload=b"test-data"):
    client.put_object(
        bucket,
        object_name,
        BytesIO(payload),
        length=len(payload),
        content_type="application/octet-stream",
    )


def test_delete_is_owner_scoped_and_returns_pending_until_worker_purges(
    app, client, monkeypatch
):
    owner_id, owner_headers = _register(client, "run-delete-owner")
    _, other_headers = _register(client, "run-delete-other")
    run = _create_run(client, owner_headers, monkeypatch)
    run_oid = ObjectId(run["id"])
    account_oid = ObjectId(run["account_id"])

    denied = client.delete(
        f"/api/backtest/runs/{run['id']}", headers=other_headers
    )
    assert denied.status_code == 404

    accepted = client.delete(
        f"/api/backtest/runs/{run['id']}", headers=owner_headers
    )
    assert accepted.status_code == 202
    assert accepted.json["run"]["status"] == "deleting"

    repeated = client.delete(
        f"/api/backtest/runs/{run['id']}", headers=owner_headers
    )
    assert repeated.status_code == 202
    assert repeated.json["run"]["status"] == "deleting"

    for path, method, payload in (
        (f"/api/backtest/runs/{run['id']}/candles?date=2026-01-05", "get", None),
        (f"/api/backtest/runs/{run['id']}/chart-workspace", "get", None),
        (f"/api/backtest/runs/{run['id']}/chart-workspace", "put", {}),
        (f"/api/backtest/runs/{run['id']}/drawings?interval_minutes=1", "put", {}),
        (f"/api/backtest/runs/{run['id']}/replay-position", "put", {}),
    ):
        response = getattr(client, method)(
            path, json=payload, headers=owner_headers
        )
        assert response.status_code in {404, 409}

    listed = client.get("/api/backtest/runs", headers=owner_headers)
    assert [item["id"] for item in listed.json["runs"]] == [run["id"]]
    assert listed.json["runs"][0]["status"] == "deleting"
    mode = client.put(
        "/api/workspace/mode",
        json={"active_mode": "backtest"},
        headers=owner_headers,
    )
    assert mode.status_code == 200
    visible_accounts = client.get("/api/accounts", headers=owner_headers)
    assert visible_accounts.status_code == 200
    assert all(
        account["id"] != run["account_id"]
        for account in visible_accounts.json["accounts"]
    )
    hidden_trades = client.get(
        f"/api/trades?account={run['account_id']}", headers=owner_headers
    )
    assert hidden_trades.status_code == 200
    assert hidden_trades.json["trades"] == []
    with app.app_context():
        stored_run = mongo.db.backtest_runs.find_one({"_id": run_oid})
        stored_account = mongo.db.trade_accounts.find_one(
            {"_id": account_oid}
        )
        assert stored_run["status"] == "deleting"
        assert stored_run["deletion_requested_by"] == ObjectId(owner_id)
        assert stored_account["status"] == "deleting"


def test_worker_physically_removes_run_account_trades_and_every_minio_object(
    app, client, monkeypatch
):
    from app.backtests.worker import BacktestWorker
    from app.models.trade_account import create_trade_account_doc
    from app.storage import get_bucket, get_client, get_market_data_bucket

    owner_id, headers = _register(client, "run-delete-cascade")
    run = _create_run(client, headers, monkeypatch)
    run_oid = ObjectId(run["id"])
    user_oid = ObjectId(owner_id)
    account_oid = ObjectId(run["account_id"])
    trade_oid = ObjectId()
    media_oid = ObjectId()
    prefix = f"backtests/{owner_id}/{run['id']}/"
    media_key = f"trades/{owner_id}/{trade_oid}/evidence.png"

    with app.app_context():
        mongo.db.backtest_runs.update_one(
            {"_id": run_oid},
            {
                "$set": {
                    "status": "ready",
                    "snapshot": {"object_key": f"{prefix}snapshot/main.parquet"},
                }
            },
        )
        mongo.db.backtest_preparation_jobs.update_one(
            {"run_id": run_oid}, {"$set": {"state": "completed"}}
        )
        mongo.db.backtest_chart_tabs.insert_one(
            {"user_id": user_oid, "run_id": run_oid, "id": "chart-1"}
        )
        mongo.db.backtest_chart_workspaces.insert_one(
            {"user_id": user_oid, "run_id": run_oid, "id": str(run_oid)}
        )
        mongo.db.backtest_drawing_states.insert_one(
            {
                "user_id": user_oid,
                "run_id": run_oid,
                "interval_minutes": 1,
            }
        )
        mongo.db.trades.insert_one(
            {
                "_id": trade_oid,
                "user_id": user_oid,
                "trade_account_id": account_oid,
                "status": "closed",
                "import_batch_id": None,
            }
        )
        mongo.db.executions.insert_one(
            {"_id": ObjectId(), "trade_id": trade_oid}
        )
        mongo.db.media.insert_one(
            {
                "_id": media_oid,
                "user_id": user_oid,
                "trade_id": trade_oid,
                "object_key": media_key,
            }
        )
        real_account = create_trade_account_doc(
            user_id=user_oid,
            account_name="real-account",
            display_name="same instrument",
            source_platform="manual",
        )
        real_account.update(
            {"_id": ObjectId(), "workspace_mode": "real"}
        )
        mongo.db.trade_accounts.insert_one(real_account)

        client_obj = get_client()
        market_bucket = get_market_data_bucket()
        _put_object(client_obj, market_bucket, f"{prefix}staging/orphan.parquet")
        _put_object(client_obj, market_bucket, f"{prefix}snapshot/main.parquet")
        _put_object(client_obj, market_bucket, f"{prefix}unexpected/extra.bin")
        _put_object(client_obj, get_bucket(), media_key)

    accepted = client.delete(
        f"/api/backtest/runs/{run['id']}", headers=headers
    )
    assert accepted.status_code == 202
    clock = _Clock()
    with app.app_context():
        assert BacktestWorker(clock=clock, worker_id="purge-worker").process_one()

        assert mongo.db.backtest_runs.find_one({"_id": run_oid}) is None
        assert mongo.db.trade_accounts.find_one({"_id": account_oid}) is None
        assert mongo.db.trades.find_one({"_id": trade_oid}) is None
        assert mongo.db.executions.count_documents({"trade_id": trade_oid}) == 0
        assert mongo.db.media.find_one({"_id": media_oid}) is None
        assert mongo.db.backtest_preparation_jobs.count_documents(
            {"run_id": run_oid}
        ) == 0
        for collection in (
            "backtest_chart_tabs",
            "backtest_chart_workspaces",
            "backtest_drawing_states",
        ):
            assert mongo.db[collection].count_documents({"run_id": run_oid}) == 0
        assert list(
            get_client().list_objects(
                get_market_data_bucket(), prefix=prefix, recursive=True
            )
        ) == []
        assert (get_bucket(), media_key) not in get_client().objects
        assert mongo.db.trade_accounts.find_one({"_id": real_account["_id"]})

    assert client.get("/api/backtest/runs", headers=headers).json["runs"] == []


def test_deletion_waits_for_live_preparation_lease_then_resumes(app, client, monkeypatch):
    from app.backtests.worker import BacktestWorker

    _, headers = _register(client, "run-delete-live-lease")
    run = _create_run(client, headers, monkeypatch)
    run_oid = ObjectId(run["id"])
    clock = _Clock()
    live_until = clock.now + timedelta(seconds=30)

    with app.app_context():
        mongo.db.backtest_runs.update_one(
            {"_id": run_oid},
            {
                "$set": {
                    "preparation_lease_owner": "old-worker",
                    "preparation_lease_expires_at": live_until,
                }
            },
        )
        mongo.db.backtest_preparation_jobs.update_one(
            {"run_id": run_oid},
            {
                "$set": {
                    "state": "running",
                    "lease_owner": "old-worker",
                    "lease_expires_at": live_until,
                }
            },
        )

    assert client.delete(
        f"/api/backtest/runs/{run['id']}", headers=headers
    ).status_code == 202
    with app.app_context():
        worker = BacktestWorker(
            provider=object(), clock=clock, worker_id="replacement-worker"
        )
        assert worker.process_one() is False
        assert mongo.db.backtest_runs.find_one({"_id": run_oid})["status"] == "deleting"

        clock.advance(31)
        assert worker.process_one() is True
        assert mongo.db.backtest_runs.find_one({"_id": run_oid}) is None
        assert mongo.db.backtest_preparation_jobs.find_one({"run_id": run_oid}) is None


def test_stale_preparation_worker_removes_an_object_written_after_deletion(
    app, client, monkeypatch
):
    from app.backtests.worker import BacktestWorker, LeaseLostError
    from app.storage import get_client, get_market_data_bucket

    _, headers = _register(client, "run-delete-late-write")
    run_summary = _create_run(client, headers, monkeypatch)
    run_id = run_summary["id"]
    run_oid = ObjectId(run_id)
    # Use the stored owner id so the object key matches the run namespace.
    with app.app_context():
        stored_run = mongo.db.backtest_runs.find_one({"_id": run_oid})
        user_id = str(stored_run["user_id"])

    assert client.delete(
        f"/api/backtest/runs/{run_id}", headers=headers
    ).status_code == 202
    late_key = f"backtests/{user_id}/{run_id}/staging/late.parquet"
    with app.app_context():
        _put_object(get_client(), get_market_data_bucket(), late_key)
        worker = BacktestWorker(worker_id="stale-preparation-worker")

        def lost_lease(*_args):
            raise LeaseLostError("stale preparation lease")

        monkeypatch.setattr(worker, "_renew_or_lose", lost_lease)
        try:
            worker._verify_preparation_write(
                {}, stored_run, type("Heartbeat", (), {"check": lambda self: None})(), late_key
            )
        except LeaseLostError:
            pass
        else:
            raise AssertionError("A stale worker must not continue publishing")

        assert list(
            get_client().list_objects(
                get_market_data_bucket(), prefix=late_key, recursive=True
            )
        ) == []


def test_cleanup_failure_leaves_run_for_a_new_worker_to_finish(
    app, client, monkeypatch
):
    from app.backtests.worker import BacktestWorker
    from app.storage import get_bucket, get_client

    _, headers = _register(client, "run-delete-recovery")
    run = _create_run(client, headers, monkeypatch)
    run_oid = ObjectId(run["id"])
    trade_oid = ObjectId()
    account_oid = ObjectId(run["account_id"])
    media_key = f"trades/{headers['Authorization'][-10:]}/{trade_oid}/x.png"

    with app.app_context():
        mongo.db.backtest_runs.update_one({"_id": run_oid}, {"$set": {"status": "ready"}})
        mongo.db.trade_accounts.update_one({"_id": account_oid}, {"$set": {"status": "active"}})
        user_id = str(
            mongo.db.users.find_one({"username": "run-delete-recovery"})["_id"]
        )
        user_oid = ObjectId(user_id)
        mongo.db.trades.insert_one(
            {
                "_id": trade_oid,
                "user_id": user_oid,
                "trade_account_id": account_oid,
                "status": "closed",
                "import_batch_id": None,
            }
        )
        mongo.db.media.insert_one(
            {
                "_id": ObjectId(),
                "user_id": user_oid,
                "trade_id": trade_oid,
                "object_key": media_key,
            }
        )
        _put_object(get_client(), get_bucket(), media_key)
        original_remove = get_client()._remove_object
        should_fail = {"once": True}

        def fail_once(bucket, object_name):
            if object_name == media_key and should_fail["once"]:
                should_fail["once"] = False
                raise RuntimeError("temporary MinIO outage")
            return original_remove(bucket, object_name)

        get_client().remove_object.side_effect = fail_once

    assert client.delete(
        f"/api/backtest/runs/{run['id']}", headers=headers
    ).status_code == 202
    with app.app_context():
        first_worker = BacktestWorker(worker_id="first-worker")
        try:
            first_worker.process_one()
        except RuntimeError as exc:
            assert "temporary MinIO outage" in str(exc)
        else:
            raise AssertionError("MinIO removal failure should be retried")

        assert mongo.db.backtest_runs.find_one({"_id": run_oid})["status"] == "deleting"
        assert mongo.db.trades.find_one({"_id": trade_oid}) is not None
        assert mongo.db.media.find_one({"trade_id": trade_oid}) is not None

        second_worker = BacktestWorker(worker_id="replacement-worker")
        assert second_worker.process_one() is True
        assert mongo.db.backtest_runs.find_one({"_id": run_oid}) is None
        assert mongo.db.trades.find_one({"_id": trade_oid}) is None
        assert mongo.db.media.count_documents({"trade_id": trade_oid}) == 0
