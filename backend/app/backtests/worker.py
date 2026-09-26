"""Lease-based worker for durable Backtest market-data preparation."""

from __future__ import annotations

import os
import threading
import time as time_module
import uuid
from datetime import date, datetime, time, timedelta, timezone

from bson import ObjectId
from flask import current_app, has_app_context

from app.backtests.dukascopy_provider import DukascopyProvider
from app.backtests.repository import (
    BacktestRepository,
    PreparationJobRepository,
)
from app.backtests.snapshot_store import SnapshotStore
from app.utils.datetime_utils import utc_now


class LeaseLostError(RuntimeError):
    """Raised when another worker has fenced off this lease holder."""


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _date_instant(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


class _LeaseHeartbeat:
    """Renew a live Mongo lease during long date downloads/assembly."""

    def __init__(self, worker, job_id, run_id, user_id, worker_id, app):
        self.worker = worker
        self.job_id = job_id
        self.run_id = run_id
        self.user_id = user_id
        self.worker_id = worker_id
        self.app = app
        self.stop_event = threading.Event()
        self.lost = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name=f"backtest-lease-{job_id}",
            daemon=True,
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def check(self):
        if self.lost.is_set():
            raise LeaseLostError("Backtest preparation lease was lost.")

    def _run(self):
        interval = max(1, min(30, self.worker.lease_seconds // 3))
        while not self.stop_event.wait(interval):
            try:
                with self.app.app_context():
                    self.worker._renew_leases(
                        self.job_id,
                        self.run_id,
                        self.user_id,
                        self.worker_id,
                    )
            except LeaseLostError:
                self.lost.set()
                return
            except Exception:
                # A transient Mongo hiccup should not immediately discard a
                # still-valid lease; the next heartbeat can retry.
                continue


class BacktestWorker:
    """Claim and process one durable preparation job at a time."""

    def __init__(
        self,
        provider=None,
        clock=None,
        *,
        repository=None,
        job_repository=None,
        snapshot_store=None,
        worker_id: str | None = None,
        lease_seconds: int | None = None,
    ):
        self.provider = provider or DukascopyProvider()
        self.clock = clock or utc_now
        self.repository = repository or BacktestRepository()
        self.job_repository = job_repository or PreparationJobRepository()
        self.snapshot_store = snapshot_store or SnapshotStore()
        self.worker_id = worker_id or f"{os.getpid()}-{uuid.uuid4().hex}"
        self.lease_seconds = int(
            lease_seconds
            or os.environ.get("BACKTEST_JOB_LEASE_SECONDS", "300")
        )

    def process_one(self) -> bool:
        """Process one claimed job; return False when the queue is empty."""
        if not has_app_context():
            raise RuntimeError(
                "BacktestWorker.process_one requires a Flask application context."
            )
        now = _as_utc(self.clock())
        candidate = self.job_repository.find_candidate(now=now)
        if candidate is None:
            return False

        job_id = candidate["_id"]
        user_id = candidate["user_id"]
        run_id = candidate["run_id"]
        user_id_text = str(user_id)
        run = self.repository.find_owned_run(user_id_text, run_id)
        if run is None:
            if candidate.get("terminal_outcome"):
                cleanup_job = self.job_repository.claim_terminal_cleanup(
                    job_id,
                    self.worker_id,
                    now=now,
                    lease_seconds=self.lease_seconds,
                )
                if cleanup_job is not None:
                    self._finish_orphan_terminal(cleanup_job)
                return True
            self.job_repository.delete_for_run(run_id)
            return True
        if run.get("status") == "ready":
            self.job_repository.mark_recovered_completed(
                run_id, now=_as_utc(self.clock())
            )
            return True

        leased_run = self.repository.claim_preparation_lease(
            user_id,
            run_id,
            self.worker_id,
            now=now,
            lease_seconds=self.lease_seconds,
        )
        if leased_run is None:
            return False

        if candidate.get("terminal_outcome"):
            job = self.job_repository.claim_terminal_cleanup(
                job_id,
                self.worker_id,
                now=now,
                lease_seconds=self.lease_seconds,
            )
        else:
            job = self.job_repository.claim(
                job_id,
                self.worker_id,
                now=now,
                lease_seconds=self.lease_seconds,
            )
        if job is None:
            self.repository.release_preparation_lease(run_id, self.worker_id)
            return False

        app = current_app._get_current_object()
        heartbeat = _LeaseHeartbeat(
            self, job_id, run_id, user_id, self.worker_id, app
        )
        heartbeat.start()
        try:
            if job.get("terminal_outcome"):
                self._finish_outcome(leased_run, job, heartbeat)
            else:
                self._process_claimed(job, leased_run, heartbeat)
        except LeaseLostError:
            # A new owner is processing this job; leave its run and checkpoint
            # intact for that owner.
            return True
        finally:
            heartbeat.stop()
        return True

    def _process_claimed(self, job: dict, run: dict, heartbeat) -> None:
        run_id = run["_id"]
        user_id = run["user_id"]
        user_id_text = str(user_id)
        first_requested_date = datetime.fromtimestamp(
            int(run["start_utc_ms"]) / 1000, tz=timezone.utc
        ).date()
        last_requested_date = _as_date(job["end_utc_date"])
        all_dates = self._date_range(
            _as_date(job["next_utc_date"]), last_requested_date
        )
        completed = {
            _as_date(checkpoint["utc_date"]): checkpoint
            for checkpoint in job.get("completed_utc_dates", [])
        }
        total_dates = max(
            (last_requested_date - first_requested_date).days + 1, 1
        )

        for utc_date in all_dates:
            heartbeat.check()
            if utc_date in completed:
                continue
            done_count = len(completed)
            self._renew_or_lose(job, run, heartbeat)
            if not self.repository.update_leased_progress(
                user_id_text,
                run_id,
                self.worker_id,
                stage="downloading",
                percent=min(90, round(done_count * 90 / total_dates, 2)),
                now=_as_utc(self.clock()),
            ):
                raise LeaseLostError("Backtest preparation lease was lost.")
            try:
                result = self.provider.fetch_day(run["instrument"], utc_date)
                candles = self._validated_candles(result, utc_date, run)
            except Exception as exc:
                self._renew_or_lose(job, run, heartbeat)
                terminal_job = self.job_repository.mark_terminal(
                    job["_id"],
                    self.worker_id,
                    now=_as_utc(self.clock()),
                    outcome="failed",
                    error_type=type(exc).__name__,
                )
                if terminal_job is None:
                    raise LeaseLostError(
                        "Preparation lease expired before failure cleanup."
                    ) from exc
                self._finish_outcome(run, terminal_job, heartbeat)
                return

            outcome = "data" if candles else "empty"
            object_key = self.snapshot_store.write_staged_date(
                user_id,
                run_id,
                utc_date,
                candles,
                before_write=lambda: self._renew_or_lose(
                    job, run, heartbeat
                ),
            )
            next_date = utc_date + timedelta(days=1)
            now = _as_utc(self.clock())
            self._renew_or_lose(job, run, heartbeat)
            checkpointed = self.job_repository.add_checkpoint(
                job["_id"],
                self.worker_id,
                now=now,
                utc_date=_date_instant(utc_date),
                outcome=outcome,
                object_key=object_key,
                next_utc_date=_date_instant(next_date),
            )
            if not checkpointed:
                raise LeaseLostError("Backtest preparation lease was lost.")
            completed[utc_date] = {
                "utc_date": _date_instant(utc_date),
                "outcome": outcome,
                "object_key": object_key,
            }

        self._renew_or_lose(job, run, heartbeat)
        latest_job = self.job_repository.collection.find_one(
            {"_id": job["_id"], "lease_owner": self.worker_id}
        )
        if latest_job is None:
            raise LeaseLostError("Backtest preparation lease was lost.")
        checkpoints = latest_job.get("completed_utc_dates", [])
        if not self.repository.update_leased_progress(
            user_id_text,
            run_id,
            self.worker_id,
            stage="assembling",
            percent=95,
            now=_as_utc(self.clock()),
        ):
            raise LeaseLostError("Backtest preparation lease was lost.")
        snapshot, coverage = self.snapshot_store.assemble_snapshot(
            user_id=user_id,
            run=run,
            completed_dates=checkpoints,
            before_publish=lambda: self._renew_or_lose(job, run, heartbeat),
        )
        if not snapshot.get("candle_count"):
            self._renew_or_lose(job, run, heartbeat)
            terminal_job = self.job_repository.mark_terminal(
                job["_id"],
                self.worker_id,
                now=_as_utc(self.clock()),
                outcome="no_data",
            )
            if terminal_job is None:
                raise LeaseLostError(
                    "Preparation lease expired before no-data cleanup."
                )
            self._finish_outcome(run, terminal_job, heartbeat)
            return

        self._renew_or_lose(job, run, heartbeat)
        ready = self.repository.mark_ready(
            user_id_text,
            run_id,
            snapshot=snapshot,
            coverage=coverage,
            first_time_ms=snapshot["first_time_ms"],
            worker_id=self.worker_id,
            now=_as_utc(self.clock()),
        )
        if not ready:
            current_run = self.repository.find_owned_run(user_id_text, run_id)
            if not current_run or current_run.get("status") != "ready":
                raise LeaseLostError("Backtest run could not be committed by this worker.")
        self.repository.create_default_chart_tab(user_id_text, run_id)
        if not self.job_repository.mark_completed(
            job["_id"], self.worker_id, now=_as_utc(self.clock())
        ):
            raise LeaseLostError("Backtest preparation lease was lost after publish.")

    def _finish_outcome(
        self,
        run: dict,
        job: dict,
        heartbeat,
    ) -> None:
        """Commit a previously fenced terminal result and clean up idempotently."""
        user_id = run["user_id"]
        run_id = run["_id"]
        self._renew_or_lose(job, run, heartbeat)
        now = _as_utc(self.clock())
        outcome = job.get("terminal_outcome")
        no_data = outcome == "no_data"
        removed = self.repository.delete_leased_run(
            str(user_id),
            run_id,
            self.worker_id,
            now=now,
        )
        if not removed and self.repository.find_owned_run(str(user_id), run_id):
            raise LeaseLostError(
                "The run lease expired before terminal cleanup."
            )
        self._finish_terminal_cleanup(job, run)

    def _finish_orphan_terminal(self, job: dict) -> None:
        """Complete idempotent notice/object cleanup after a prior run delete."""
        user_id = job["user_id"]
        run_id = job["run_id"]
        self.repository.cleanup_orphan_associations(user_id, run_id)
        self._finish_terminal_cleanup(job, None)

    def _finish_terminal_cleanup(self, job: dict, run: dict | None) -> None:
        user_id = job["user_id"]
        run_id = job["run_id"]
        outcome = job["terminal_outcome"]
        no_data = outcome == "no_data"
        now = _as_utc(self.clock())
        self.repository.add_notice(
            {
                "_id": job["terminal_notice_id"],
                "user_id": user_id,
                "run_id": run_id,
                "instrument": (
                    run["instrument"]
                    if run
                    else job.get("instrument", "Unknown instrument")
                ),
                "requested_start_date": (
                    run["requested_start_date"]
                    if run
                    else job.get("requested_start_date", "")
                ),
                "requested_end_date": (
                    run["requested_end_date"]
                    if run
                    else job.get("requested_end_date", "")
                ),
                "outcome": "no_data" if no_data else "failed",
                "next_action": "edit_range" if no_data else "start_new_run",
                "message": (
                    "No candles were available for the selected range."
                    if no_data
                    else "Market-data preparation failed."
                ),
                "error_type": job.get("terminal_error_type"),
                "dismissed": False,
                "created_at": now,
                "updated_at": now,
            }
        )
        self.snapshot_store.remove_run_objects(user_id, run_id)
        self.job_repository.delete_for_run(run_id)

    def _renew_leases(self, job_id, run_id, user_id, worker_id) -> None:
        now = _as_utc(self.clock())
        if not self.repository.renew_preparation_lease(
            user_id,
            run_id,
            worker_id,
            now=now,
            lease_seconds=self.lease_seconds,
        ):
            raise LeaseLostError("Backtest run lease was lost.")
        if not self.job_repository.renew_lease(
            job_id,
            worker_id,
            now=now,
            lease_seconds=self.lease_seconds,
        ):
            self.repository.release_preparation_lease(run_id, worker_id)
            raise LeaseLostError("Backtest preparation job lease was lost.")

    def _renew_or_lose(self, job: dict, run: dict, heartbeat) -> None:
        heartbeat.check()
        self._renew_leases(
            job["_id"], run["_id"], run["user_id"], self.worker_id
        )

    @staticmethod
    def _date_range(start: date, end: date) -> list[date]:
        if end < start:
            return []
        count = (end - start).days + 1
        return [start + timedelta(days=offset) for offset in range(count)]

    @staticmethod
    def _validated_candles(result, utc_date: date, run: dict) -> list[dict]:
        if not isinstance(result, dict) or _as_date(result.get("utc_date")) != utc_date:
            raise ValueError("Downloader returned an unexpected UTC date.")
        if result.get("outcome") not in {"data", "empty"}:
            raise ValueError("Downloader returned an invalid date outcome.")
        candles = result.get("candles")
        if not isinstance(candles, list):
            raise ValueError("Downloader returned an invalid candle list.")
        normalized = []
        seen = set()
        start_ms = int(run["start_utc_ms"])
        end_ms = int(run["end_utc_ms"])
        for candle in candles:
            if not isinstance(candle, dict):
                raise ValueError("Downloader returned a malformed candle.")
            timestamp = int(candle["time_ms"])
            # The provider reads whole UTC days. Enforce the run's exact local
            # calendar selection here so edge-day bars outside [start,end)
            # never enter the staging object or immutable snapshot.
            if timestamp < start_ms or timestamp >= end_ms:
                continue
            if timestamp in seen:
                continue
            seen.add(timestamp)
            row = {"time_ms": timestamp}
            for key in ("open", "high", "low", "close"):
                row[key] = float(candle[key])
            if "volume" in candle and candle["volume"] is not None:
                row["volume"] = float(candle["volume"])
            normalized.append(row)
        normalized.sort(key=lambda item: item["time_ms"])
        return normalized


def run_worker_forever() -> None:
    """Run the independent worker process until it receives a stop signal."""
    from app import create_app

    app = create_app()
    worker = BacktestWorker()
    idle_sleep = float(os.environ.get("BACKTEST_WORKER_POLL_SECONDS", "2"))
    with app.app_context():
        while True:
            try:
                processed = worker.process_one()
            except Exception:
                app.logger.exception("Backtest preparation worker iteration failed")
                processed = False
            if not processed:
                time_module.sleep(idle_sleep)


if __name__ == "__main__":
    run_worker_forever()
