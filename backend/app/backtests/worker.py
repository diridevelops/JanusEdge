"""Lease-based worker for durable Backtest market-data preparation."""

from __future__ import annotations

import math
import os
import random
import threading
import time as time_module
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from flask import current_app, has_app_context

from app.backtests.dukascopy_provider import DukascopyProvider
from app.backtests.repository import (
    BacktestRepository,
    PreparationJobRepository,
)
from app.backtests.snapshot_store import SnapshotStore
from app.extensions import mongo
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


class _DeletionLeaseHeartbeat:
    """Renew a deletion lease while MinIO/trade cleanup is in progress."""

    def __init__(self, worker, run, app):
        self.worker = worker
        self.run = run
        self.app = app
        self.stop_event = threading.Event()
        self.lost = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name=f"backtest-delete-{run['_id']}",
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
            raise LeaseLostError("Backtest deletion lease was lost.")

    def _run(self):
        interval = max(1, min(30, self.worker.lease_seconds // 3))
        while not self.stop_event.wait(interval):
            try:
                with self.app.app_context():
                    renewed = self.worker.repository.renew_deletion_lease(
                        self.run["user_id"],
                        self.run["_id"],
                        self.worker.worker_id,
                        now=_as_utc(self.worker.clock()),
                        lease_seconds=self.worker.lease_seconds,
                    )
                if not renewed:
                    self.lost.set()
                    return
            except Exception:
                # A transient database interruption may still leave the lease
                # live; the owner check fences any later renewal.
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
        random_source=None,
        worker_id: str | None = None,
        lease_seconds: int | None = None,
    ):
        self.provider = provider or DukascopyProvider()
        self.clock = clock or utc_now
        self.repository = repository or BacktestRepository()
        self.job_repository = job_repository or PreparationJobRepository()
        self.snapshot_store = snapshot_store or SnapshotStore()
        self.random_source = random_source or random.SystemRandom()
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
        if self._process_deleting_run(now):
            return True
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
            elif job.get("selection"):
                if job["selection"].get("status") in {"searching", "selected"}:
                    selected = self._process_random_selection(
                        job, leased_run, heartbeat
                    )
                    if selected is None:
                        return True
                    job, leased_run = selected
                self._process_claimed(job, leased_run, heartbeat)
            else:
                self._process_claimed(job, leased_run, heartbeat)
        except LeaseLostError:
            # A new owner is processing this job; leave its run and checkpoint
            # intact for that owner.
            return True
        finally:
            heartbeat.stop()
            current_run = self.repository.find_owned_run(
                user_id_text, run_id
            )
            if current_run and current_run.get("status") == "deleting":
                self.repository.release_preparation_lease(
                    run_id, self.worker_id
                )
        return True

    def _process_deleting_run(self, now) -> bool:
        """Resume one confirmed deletion before claiming preparation work."""
        candidate = self.repository.find_deletion_candidate(now=now)
        if candidate is None:
            return False
        run = self.repository.claim_deletion_lease(
            candidate["user_id"],
            candidate["_id"],
            self.worker_id,
            now=now,
            lease_seconds=self.lease_seconds,
        )
        if run is None:
            return False

        heartbeat = _DeletionLeaseHeartbeat(
            self, run, current_app._get_current_object()
        )
        heartbeat.start()
        try:
            self._finish_deletion(run, heartbeat)
        except LeaseLostError:
            return True
        except Exception:
            self.repository.release_deletion_lease(
                run["user_id"], run["_id"], self.worker_id
            )
            raise
        finally:
            heartbeat.stop()
        return True

    def _finish_deletion(self, run: dict, heartbeat) -> None:
        """Purge external and related records before removing the run marker."""
        from app.trades.service import TradeService

        user_id = str(run["user_id"])
        run_id = run["_id"]
        heartbeat.check()
        self.snapshot_store.remove_run_objects(run["user_id"], run_id)
        heartbeat.check()

        accounts = list(
            mongo.db.trade_accounts.find(
                {
                    "user_id": run["user_id"],
                    "workspace_mode": "backtest",
                    "backtest_run_id": run_id,
                }
            )
        )
        account_ids = {account["_id"] for account in accounts}
        if run.get("account_id") is not None:
            account_id = run["account_id"]
            account_ids.add(
                account_id
                if isinstance(account_id, ObjectId)
                else ObjectId(str(account_id))
            )

        trade_service = TradeService()
        for account_id in sorted(account_ids, key=str):
            heartbeat.check()
            trade_service.delete_backtest_account_trades(
                user_id, account_id, before_each=heartbeat.check
            )
        remaining_trade_count = mongo.db.trades.count_documents(
            {
                "user_id": run["user_id"],
                "trade_account_id": {"$in": list(account_ids)},
            }
        )
        if remaining_trade_count:
            raise RuntimeError(
                "Backtest run cleanup left linked trades behind."
            )

        heartbeat.check()
        completed = self.repository.finish_deletion(
            run["user_id"],
            run_id,
            self.worker_id,
            now=_as_utc(self.clock()),
        )
        if not completed and self.repository.find_owned_run(user_id, run_id):
            raise LeaseLostError("Backtest deletion lease expired before completion.")

    def _process_random_selection(
        self, job: dict, run: dict, heartbeat
    ) -> tuple[dict, dict] | None:
        """Search persisted candidates and hand a hit to normal preparation."""
        selection = dict(job["selection"])
        if selection.get("status") == "selected":
            return self._commit_selected_period(job, run, selection, heartbeat)

        minimum = _as_date(selection["minimum_start_date"])
        maximum = _as_date(selection["maximum_start_date"])
        period_months = int(selection["period_months"])

        while True:
            heartbeat.check()
            if selection.get("current_year") is None:
                years_remaining = list(selection.get("years_remaining", []))
                if not years_remaining:
                    message = (
                        "No start date with COMB one-minute candles was found "
                        f"for a {period_months}-month period."
                    )
                    self._renew_or_lose(job, run, heartbeat)
                    terminal_job = self.job_repository.mark_terminal(
                        job["_id"],
                        self.worker_id,
                        now=_as_utc(self.clock()),
                        outcome="no_data",
                        terminal_message=message,
                    )
                    if terminal_job is None:
                        raise LeaseLostError(
                            "Selection lease expired before no-data cleanup."
                        )
                    self._finish_outcome(run, terminal_job, heartbeat)
                    return None

                selected_year = self.random_source.choice(years_remaining)
                years_remaining.remove(selected_year)
                selection.update(
                    {
                        "years_remaining": years_remaining,
                        "current_year": selected_year,
                        "tried_dates": [],
                        "pending_date": None,
                    }
                )
                self._save_selection_state(job, selection, heartbeat)

            current_year = int(selection["current_year"])
            year_start = max(minimum, date(current_year, 1, 1))
            year_end = min(maximum, date(current_year, 12, 31))
            tried_dates = list(selection.get("tried_dates", []))
            candidates = [
                day
                for day in self._date_range(year_start, year_end)
                if day.isoformat() not in tried_dates
            ]
            if not candidates:
                selection.update(
                    {"current_year": None, "tried_dates": [], "pending_date": None}
                )
                self._save_selection_state(job, selection, heartbeat)
                continue

            pending = selection.get("pending_date")
            candidate_date = (
                _as_date(pending)
                if pending
                else self.random_source.choice(candidates)
            )
            if pending is None:
                selection["pending_date"] = candidate_date.isoformat()
                self._save_selection_state(job, selection, heartbeat)

            try:
                has_candles = self._probe_local_date(
                    run["instrument"],
                    candidate_date,
                    ZoneInfo(run["display_timezone"]),
                    job,
                    run,
                    heartbeat,
                )
            except LeaseLostError:
                raise
            except Exception as exc:
                self._renew_or_lose(job, run, heartbeat)
                terminal_job = self.job_repository.mark_terminal(
                    job["_id"],
                    self.worker_id,
                    now=_as_utc(self.clock()),
                    outcome="failed",
                    error_type=type(exc).__name__,
                    terminal_message=(
                        "Market-data preparation failed while searching for a "
                        f"{period_months}-month random period."
                    ),
                )
                if terminal_job is None:
                    raise LeaseLostError(
                        "Selection lease expired before failure cleanup."
                    ) from exc
                self._finish_outcome(run, terminal_job, heartbeat)
                return None

            if has_candles:
                from app.backtests.service import _random_period_end

                end_date = _random_period_end(candidate_date, period_months)
                selection.update(
                    {
                        "status": "selected",
                        "selected_start_date": candidate_date.isoformat(),
                        "selected_end_date": end_date.isoformat(),
                        "account_id": str(ObjectId()),
                        "pending_date": None,
                    }
                )
                self._save_selection_state(job, selection, heartbeat)
                job["selection"] = selection
                return self._commit_selected_period(
                    job, run, selection, heartbeat
                )

            if candidate_date.isoformat() not in tried_dates:
                tried_dates.append(candidate_date.isoformat())
            selection["tried_dates"] = tried_dates
            selection["pending_date"] = None
            if len(tried_dates) >= 10:
                selection["current_year"] = None
                selection["tried_dates"] = []
            self._save_selection_state(job, selection, heartbeat)

    def _save_selection_state(self, job: dict, selection: dict, heartbeat) -> None:
        current_run = self.repository.find_owned_run(
            str(job["user_id"]), job["run_id"]
        )
        if current_run is None:
            raise LeaseLostError("Backtest run was removed during selection.")
        self._renew_or_lose(job, current_run, heartbeat)
        if not self.job_repository.save_selection_state(
            job["_id"],
            self.worker_id,
            selection=selection,
            now=_as_utc(self.clock()),
        ):
            raise LeaseLostError("Backtest selection job lease was lost.")
        job["selection"] = selection

    def _probe_local_date(
        self, instrument, local_date, timezone_info, job, run, heartbeat
    ) -> bool:
        """Probe all UTC dates intersecting one display-timezone calendar day."""
        start_ms, end_ms = self._local_day_utc_bounds(local_date, timezone_info)
        first_utc_date = datetime.fromtimestamp(
            start_ms / 1000, tz=timezone.utc
        ).date()
        last_utc_date = datetime.fromtimestamp(
            (end_ms - 1) / 1000, tz=timezone.utc
        ).date()
        for utc_date in self._date_range(first_utc_date, last_utc_date):
            self._renew_or_lose(job, run, heartbeat)
            result = self.provider.fetch_day(instrument, utc_date)
            if (
                not isinstance(result, dict)
                or _as_date(result.get("utc_date")) != utc_date
                or result.get("outcome") not in {"data", "empty"}
                or not isinstance(result.get("candles"), list)
            ):
                raise ValueError("Downloader returned an invalid date result.")
            candles = result["candles"]
            if (result["outcome"] == "data") != bool(candles):
                raise ValueError("Downloader date outcome disagrees with its candles.")
            for candle in candles:
                if not isinstance(candle, dict) or "time_ms" not in candle:
                    raise ValueError("Downloader returned a malformed candle.")
                try:
                    timestamp = int(candle["time_ms"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "Downloader returned a malformed candle timestamp."
                    ) from exc
                if start_ms <= timestamp < end_ms:
                    return True
        return False

    @staticmethod
    def _local_day_utc_bounds(local_date: date, timezone_info) -> tuple[int, int]:
        """Use the same local-midnight conversion as the replay date window."""
        from app.backtests.service import _as_utc_ms

        return (
            _as_utc_ms(local_date, timezone_info),
            _as_utc_ms(local_date + timedelta(days=1), timezone_info),
        )

    def _commit_selected_period(
        self, job: dict, run: dict, selection: dict, heartbeat
    ) -> tuple[dict, dict]:
        """Persist resolved bounds, create the account, and continue preparation."""
        from app.backtests.service import (
            _as_utc_ms,
            _build_backtest_account_document,
            _one_calendar_month_before,
        )
        from app.backtests.repository import _object_id

        start_date = _as_date(selection["selected_start_date"])
        end_date = _as_date(selection["selected_end_date"])
        account_id = _object_id(selection.get("account_id"))
        if account_id is None:
            raise ValueError("Selected random period has no account id.")
        timezone_info = ZoneInfo(run["display_timezone"])
        start_utc_ms = _as_utc_ms(start_date, timezone_info)
        end_utc_ms = _as_utc_ms(end_date + timedelta(days=1), timezone_info)
        context_start_date = _one_calendar_month_before(start_date)
        context_start_utc_ms = _as_utc_ms(context_start_date, timezone_info)
        context_start_utc_date = datetime.fromtimestamp(
            context_start_utc_ms / 1000, tz=timezone.utc
        ).date()
        end_utc_date = datetime.fromtimestamp(
            (end_utc_ms - 1) / 1000, tz=timezone.utc
        ).date()

        self._renew_or_lose(job, run, heartbeat)
        resolved_run = self.repository.resolve_random_selection(
            str(run["user_id"]),
            run["_id"],
            self.worker_id,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            start_utc_ms=start_utc_ms,
            end_utc_ms=end_utc_ms,
            context_start_utc_ms=context_start_utc_ms,
            now=_as_utc(self.clock()),
        )
        if resolved_run is None:
            raise LeaseLostError("Selected period could not be committed.")

        self._renew_or_lose(job, resolved_run, heartbeat)
        user_oid = resolved_run["user_id"]
        existing_account = mongo.db.trade_accounts.find_one(
            {"user_id": user_oid, "backtest_run_id": resolved_run["_id"]}
        )
        if existing_account is not None and existing_account["_id"] != account_id:
            raise RuntimeError("Run already has a different associated account.")
        if existing_account is None:
            account = _build_backtest_account_document(
                user_id=user_oid,
                run_id=resolved_run["_id"],
                account_id=account_id,
                instrument=resolved_run["instrument"],
                start_date=start_date,
                end_date=end_date,
                blind_mode=bool(resolved_run.get("blind_mode", False)),
            )
            mongo.db.trade_accounts.insert_one(account)

        current_run = self.repository.find_owned_run(
            str(user_oid), resolved_run["_id"]
        )
        if (
            current_run is None
            or current_run.get("status") != "preparing"
            or current_run.get("account_id") != account_id
        ):
            mongo.db.trade_accounts.delete_one(
                {
                    "user_id": user_oid,
                    "backtest_run_id": resolved_run["_id"],
                }
            )
            raise LeaseLostError("Run deletion fenced selected-period creation.")

        self._renew_or_lose(job, current_run, heartbeat)
        committed_job = self.job_repository.commit_selected_period(
            job["_id"],
            self.worker_id,
            start_date=start_date,
            end_date=end_date,
            context_start_utc_date=context_start_utc_date,
            end_utc_date=end_utc_date,
            now=_as_utc(self.clock()),
        )
        if committed_job is None:
            raise LeaseLostError("Selected-period preparation job was lost.")
        return committed_job, current_run

    def _process_claimed(self, job: dict, run: dict, heartbeat) -> None:
        run_id = run["_id"]
        user_id = run["user_id"]
        user_id_text = str(user_id)
        first_requested_date = _as_date(
            job.get("context_start_utc_date", job["next_utc_date"])
        )
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
                after_write=lambda key: self._verify_preparation_write(
                    job, run, heartbeat, key
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
            after_publish=lambda key: self._verify_preparation_write(
                job, run, heartbeat, key
            ),
        )
        if not snapshot.get("replay_period_candle_count"):
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

        normalization_reference = snapshot.pop(
            "_normalization_reference_price", None
        )
        if run.get("blind_mode"):
            valid_reference = (
                isinstance(normalization_reference, (int, float))
                and not isinstance(normalization_reference, bool)
                and math.isfinite(float(normalization_reference))
                and float(normalization_reference) != 0
            )
            if not valid_reference:
                self._renew_or_lose(job, run, heartbeat)
                terminal_job = self.job_repository.mark_terminal(
                    job["_id"],
                    self.worker_id,
                    now=_as_utc(self.clock()),
                    outcome="failed",
                    error_type="InvalidNormalizationReference",
                    terminal_message=(
                        "Blind mode could not normalize this run because the "
                        "first replay-period candle has a zero or non-finite "
                        "opening price."
                    ),
                )
                if terminal_job is None:
                    raise LeaseLostError(
                        "Preparation lease expired before normalization failure cleanup."
                    )
                self._finish_outcome(run, terminal_job, heartbeat)
                return

        self._renew_or_lose(job, run, heartbeat)
        ready = self.repository.mark_ready(
            user_id_text,
            run_id,
            snapshot=snapshot,
            coverage=coverage,
            warmup_coverage=snapshot["warmup_coverage"],
            replay_start_source_index=snapshot["replay_start_source_index"],
            first_time_ms=snapshot["replay_start_time_ms"],
            normalized_reference_price=(
                float(normalization_reference)
                if run.get("blind_mode")
                else None
            ),
            worker_id=self.worker_id,
            now=_as_utc(self.clock()),
        )
        if not ready:
            current_run = self.repository.find_owned_run(user_id_text, run_id)
            if not current_run or current_run.get("status") != "ready":
                raise LeaseLostError("Backtest run could not be committed by this worker.")
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
                    run.get("requested_start_date")
                    if run and run.get("requested_start_date") is not None
                    else job.get("requested_start_date", "")
                ),
                "requested_end_date": (
                    run.get("requested_end_date")
                    if run and run.get("requested_end_date") is not None
                    else job.get("requested_end_date", "")
                ),
                "period_selection": (
                    run.get("period_selection", "manual")
                    if run
                    else "random" if job.get("selection") else "manual"
                ),
                "period_months": (
                    run.get("period_months")
                    if run
                    else (job.get("selection") or {}).get("period_months")
                ),
                "blind_mode": bool(
                    (run or {}).get("blind_mode", job.get("blind_mode", False))
                ),
                "outcome": "no_data" if no_data else "failed",
                "next_action": (
                    "edit_range"
                    if no_data
                    and (run or {}).get("period_selection") != "random"
                    else "start_new_run"
                ),
                "message": job.get("terminal_message")
                or (
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

    def _verify_preparation_write(
        self, job: dict, run: dict, heartbeat, object_key: str
    ) -> None:
        """Fence an object PUT that overlapped run deletion or lease loss."""
        try:
            self._renew_or_lose(job, run, heartbeat)
        except LeaseLostError:
            current = self.repository.find_owned_run(
                str(run["user_id"]), run["_id"]
            )
            if current is None or current.get("status") == "deleting":
                self.snapshot_store.remove_object(object_key)
            raise

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
        start_ms = int(run.get("context_start_utc_ms", run["start_utc_ms"]))
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
