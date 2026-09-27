"""Lease expiry fencing for retries, staging, and ready publication."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from bson import ObjectId

from app.backtests.repository import PreparationJobRepository
from app.backtests.schemas import create_preparation_job_doc
from app.extensions import mongo


def test_retry_does_not_steal_a_live_worker_lease(app):
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    run_id = ObjectId()
    user_id = ObjectId()
    job = create_preparation_job_doc(
        job_id=ObjectId(),
        user_id=user_id,
        run_id=run_id,
        instrument="EUR-USD",
        requested_start_date=date(2026, 1, 5),
        requested_end_date=date(2026, 1, 5),
        context_start_utc_date=date(2026, 1, 5),
        end_utc_date=date(2026, 1, 5),
        staging_prefix=f"backtests/{user_id}/{run_id}/staging/",
    )
    job.update(
        {
            "state": "running",
            "lease_owner": "live-worker",
            "lease_expires_at": now + timedelta(minutes=5),
        }
    )
    with app.app_context():
        mongo.db.backtest_preparation_jobs.insert_one(job)
        repository = PreparationJobRepository()

        assert repository.requeue(run_id, now=now) is False
        still_leased = mongo.db.backtest_preparation_jobs.find_one(
            {"_id": job["_id"]}
        )
        assert still_leased["state"] == "running"
        assert still_leased["lease_owner"] == "live-worker"

        assert repository.requeue(
            run_id, now=now + timedelta(minutes=6)
        ) is True
        requeued = mongo.db.backtest_preparation_jobs.find_one(
            {"_id": job["_id"]}
        )
        assert requeued["state"] == "queued"
        assert requeued["lease_owner"] is None


class _Clock:
    def __init__(self):
        self.now = datetime(2026, 12, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def expire(self, seconds=61):
        self.now += timedelta(seconds=seconds)


class _Provider:
    def __init__(self, clock, *, expire_after_fetch=False, fail=False):
        self.clock = clock
        self.expire_after_fetch = expire_after_fetch
        self.fail = fail
        self.calls = []

    def fetch_day(self, instrument, utc_date):
        self.calls.append((instrument, utc_date))
        if self.expire_after_fetch:
            self.expire_after_fetch = False
            self.clock.expire()
        if self.fail:
            raise RuntimeError("provider failed after lease expiry")
        timestamp = int(
            datetime.combine(
                utc_date, datetime.min.time(), tzinfo=timezone.utc
            ).timestamp()
            * 1000
        )
        return {
            "utc_date": utc_date,
            "outcome": "data",
            "candles": [
                {
                    "time_ms": timestamp,
                    "open": 1.1,
                    "high": 1.2,
                    "low": 1.0,
                    "close": 1.15,
                    "volume": 30,
                }
            ],
        }


def _create_run(monkeypatch, app):
    import app.backtests.service as service_module

    monkeypatch.setattr(
        service_module,
        "fetch_instrument_codes",
        lambda: ["EUR-USD"],
    )
    with app.app_context():
        return service_module.BacktestService().create_run(
            user_id="507f1f77bcf86cd799439011",
            instrument="EUR-USD",
            start_date="2026-01-05",
            end_date="2026-01-05",
            display_timezone="UTC",
        )


def test_provider_error_after_expiry_cannot_delete_run_or_job(
    app, monkeypatch
):
    from app.backtests.worker import BacktestWorker

    run = _create_run(monkeypatch, app)
    clock = _Clock()
    stale_provider = _Provider(clock, expire_after_fetch=True, fail=True)
    with app.app_context():
        BacktestWorker(
            provider=stale_provider,
            clock=clock,
            worker_id="stale-worker",
            lease_seconds=60,
        ).process_one()

        persisted_run = mongo.db.backtest_runs.find_one({"_id": run["id"]})
        persisted_job = mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": run["id"]}
        )
        assert persisted_run["status"] == "preparing"
        assert persisted_job["state"] == "running"
        assert "terminal_outcome" not in persisted_job
        assert mongo.db.backtest_notices.count_documents({}) == 0

        provider = _Provider(clock)
        BacktestWorker(
            provider=provider,
            clock=clock,
            worker_id="replacement-worker",
            lease_seconds=60,
        ).process_one()
        ready_run = mongo.db.backtest_runs.find_one({"_id": run["id"]})

    assert ready_run["status"] == "ready"
    assert len(provider.calls) == 32


def test_expired_assembly_cannot_publish_ready_snapshot(app, monkeypatch):
    from app.backtests.snapshot_store import SnapshotStore
    from app.backtests.worker import BacktestWorker

    run = _create_run(monkeypatch, app)
    clock = _Clock()

    class ExpiringSnapshotStore(SnapshotStore):
        expire_during_assembly = True

        def assemble_snapshot(self, **kwargs):
            result = super().assemble_snapshot(**kwargs)
            if self.expire_during_assembly:
                self.expire_during_assembly = False
                clock.expire()
            return result

    with app.app_context():
        stale_store = ExpiringSnapshotStore()
        BacktestWorker(
            provider=_Provider(clock),
            clock=clock,
            snapshot_store=stale_store,
            worker_id="stale-publisher",
            lease_seconds=60,
        ).process_one()

        preparing = mongo.db.backtest_runs.find_one({"_id": run["id"]})
        checkpointed_job = mongo.db.backtest_preparation_jobs.find_one(
            {"run_id": run["id"]}
        )
        assert preparing["status"] == "preparing"
        assert preparing["snapshot"] is None
        assert len(checkpointed_job["completed_utc_dates"]) == 32

        replacement_store = ExpiringSnapshotStore()
        replacement_store.expire_during_assembly = False
        BacktestWorker(
            provider=_Provider(clock),
            clock=clock,
            snapshot_store=replacement_store,
            worker_id="replacement-publisher",
            lease_seconds=60,
        ).process_one()
        ready = mongo.db.backtest_runs.find_one({"_id": run["id"]})

    assert ready["status"] == "ready"
    assert ready["snapshot"]["candle_count"] == 32
    assert ready["coverage"]["candle_count"] == 1
    assert ready["warmup_coverage"]["candle_count"] == 31
    assert ready["snapshot"]["replay_start_source_index"] == 31
