"""Application service for Backtest run creation and ownership checks."""

from __future__ import annotations

import calendar
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bson import ObjectId
from app.extensions import mongo
from app.models.trade_account import create_trade_account_doc
from app.utils.datetime_utils import utc_now
from app.utils.errors import (
    ConflictError,
    MarketDataError,
    NotFoundError,
    ValidationError,
)
from app.backtests.repository import (
    BacktestRepository,
    PreparationJobRepository,
    _object_id,
)
from app.backtests.preparation_jobs import PreparationJobService
from app.backtests.snapshot_store import SnapshotStore
from app.backtests.schemas import (
    DEFAULT_CANDLEKIT_VERSION,
    DRAWING_SCHEMA_VERSION,
    MAX_DRAWING_STATE_BYTES,
    create_backtest_run_doc,
    serialize_chart_workspace,
    serialize_drawing_state,
    validate_chart_workspace,
)


def fetch_instrument_codes():
    """Load the pinned downloader catalog only when Backtest needs it."""
    try:
        from dukascopy_market_data.instruments import (
            fetch_instrument_codes as fetch,
        )
    except ImportError as exc:
        raise RuntimeError(
            "The pinned Dukascopy downloader is not installed."
        ) from exc
    return fetch()


def _parse_date(value, field_name: str) -> date:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be an ISO calendar date.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(
            f"{field_name} must be an ISO calendar date."
        ) from exc
    if parsed.isoformat() != value:
        raise ValidationError(f"{field_name} must use YYYY-MM-DD format.")
    return parsed


def _stored_utc_date(value) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _one_year_anniversary(start_date: date) -> date:
    """Return the first date outside the inclusive one-calendar-year span."""
    try:
        return start_date.replace(year=start_date.year + 1)
    except ValueError:
        # For a Feb 29 start, permit through Feb 28 of the following year.
        return date(start_date.year + 1, 3, 1)


def _one_calendar_month_before(start_date: date) -> date:
    """Subtract one calendar month, clamping to the prior month's last day."""
    month_index = start_date.year * 12 + start_date.month - 2
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(start_date.day, last_day))


def _as_utc_ms(local_date: date, timezone_info: ZoneInfo) -> int:
    local_midnight = datetime.combine(local_date, time.min).replace(
        tzinfo=timezone_info
    )
    return int(local_midnight.astimezone(timezone.utc).timestamp() * 1000)


def _require_nonnegative_int(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{field_name} must be a nonnegative integer.")
    return value


def _parse_interval_minutes(value) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise ValidationError("interval_minutes must be a whole number from 1 to 1440.")
    try:
        interval = int(value)
    except ValueError as exc:
        raise ValidationError(
            "interval_minutes must be a whole number from 1 to 1440."
        ) from exc
    if interval < 1 or interval > 1440:
        raise ValidationError("interval_minutes must be a whole number from 1 to 1440.")
    return interval


def _reject_json_constant(value):
    raise ValueError(f"Non-standard JSON constant {value} is not supported.")


class BacktestService:
    """Validate run requests and persist the run/account/job association."""

    def __init__(self, repository=None, job_repository=None, snapshot_store=None):
        self.repository = repository or BacktestRepository()
        self.job_repository = job_repository or PreparationJobRepository()
        self.snapshot_store = snapshot_store or SnapshotStore()
        self.preparation_jobs = PreparationJobService(self.job_repository)

    def get_instruments(self) -> list[str]:
        """Read the pinned downloader's currently supported instrument list."""
        try:
            codes = fetch_instrument_codes()
            return sorted(set(codes))
        except Exception as exc:
            raise MarketDataError(
                "The supported instrument catalog is unavailable."
            ) from exc

    def create_run(
        self,
        *,
        user_id: str,
        instrument: str,
        start_date: str,
        end_date: str,
        display_timezone: str,
    ) -> dict:
        """Validate and create one run, Backtest account, and durable job."""
        user_oid = _object_id(user_id)
        if user_oid is None:
            raise ValidationError("Authenticated user id is invalid.")

        if not isinstance(instrument, str) or not instrument:
            raise ValidationError("Instrument is required.")
        try:
            supported = self.get_instruments()
        except MarketDataError:
            # Do not create partial records if the current catalog is unknown.
            raise
        if instrument not in supported:
            raise ValidationError("Instrument is not in the current catalog.")

        start = _parse_date(start_date, "start_date")
        end = _parse_date(end_date, "end_date")
        if end < start:
            raise ValidationError("End date must be on or after start date.")
        latest_end = _one_year_anniversary(start) - timedelta(days=1)
        if end > latest_end:
            raise ValidationError(
                "The selected date range cannot exceed one calendar year."
            )
        if not isinstance(display_timezone, str) or not display_timezone:
            raise ValidationError("Display timezone is required.")
        try:
            timezone_info = ZoneInfo(display_timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError(
                "Display timezone must be a valid IANA timezone."
            ) from exc

        start_utc_ms = _as_utc_ms(start, timezone_info)
        context_start_date = _one_calendar_month_before(start)
        context_start_utc_ms = _as_utc_ms(context_start_date, timezone_info)
        end_utc_ms = _as_utc_ms(end + timedelta(days=1), timezone_info)
        utc_context_start_date = datetime.fromtimestamp(
            context_start_utc_ms / 1000, tz=timezone.utc
        ).date()
        utc_end_date = datetime.fromtimestamp(
            (end_utc_ms - 1) / 1000, tz=timezone.utc
        ).date()

        run_id = ObjectId()
        account_id = ObjectId()
        job_id = ObjectId()
        unique_id = str(run_id)
        account_label = (
            f"Backtest {instrument} {start.isoformat()} to "
            f"{end.isoformat()} ({unique_id})"
        )
        account = create_trade_account_doc(
            user_id=user_oid,
            account_name=account_label,
            display_name=account_label,
            source_platform="backtest",
        )
        account.update(
            {
                "_id": account_id,
                "workspace_mode": "backtest",
                "backtest_run_id": run_id,
            }
        )
        run = create_backtest_run_doc(
            run_id=run_id,
            user_id=user_oid,
            account_id=account_id,
            preparation_job_id=job_id,
            instrument=instrument,
            start_date=start,
            end_date=end,
            display_timezone=display_timezone,
            start_utc_ms=start_utc_ms,
            end_utc_ms=end_utc_ms,
            context_start_utc_ms=context_start_utc_ms,
        )
        staging_prefix = f"backtests/{user_oid}/{run_id}/staging/"
        job = self.preparation_jobs.build_for_run(
            job_id=job_id,
            user_id=user_oid,
            run_id=run_id,
            instrument=instrument,
            requested_start_date=start,
            requested_end_date=end,
            context_start_utc_date=utc_context_start_date,
            end_utc_date=utc_end_date,
            staging_prefix=staging_prefix,
        )

        # MongoDB deployments in current dev/testing do not require replica-set
        # transactions. Compensate on insertion errors so no half-created run
        # is retained; the unique run/job and account association indexes fence
        # concurrent duplicate inserts.
        inserted_run = inserted_account = inserted_job = False
        try:
            self.repository.create_run(run)
            inserted_run = True
            mongo.db.trade_accounts.insert_one(account)
            inserted_account = True
            self.preparation_jobs.create(job)
            inserted_job = True
        except Exception:
            if inserted_job:
                self.job_repository.delete_for_run(run_id)
            if inserted_account:
                mongo.db.trade_accounts.delete_one({"_id": account_id})
            if inserted_run:
                mongo.db.backtest_runs.delete_one({"_id": run_id})
            raise

        return {
            "id": run_id,
            "instrument": instrument,
            "requested_start_date": start.isoformat(),
            "requested_end_date": end.isoformat(),
            "display_timezone": display_timezone,
            "status": "preparing",
            "account_id": account_id,
            "account_label": account_label,
            "progress": run["progress"],
            "created_at": run["created_at"],
            "start_utc_ms": start_utc_ms,
            "context_start_utc_ms": context_start_utc_ms,
            "end_utc_ms": end_utc_ms,
        }

    def list_runs(self, user_id: str) -> list[dict]:
        runs = self.repository.list_by_user(user_id)
        accounts = {
            account["backtest_run_id"]: account
            for account in mongo.db.trade_accounts.find(
                {
                    "user_id": ObjectId(user_id),
                    "backtest_run_id": {"$in": [run["_id"] for run in runs]},
                }
            )
        } if runs else {}
        from app.backtests.schemas import serialize_run

        return [serialize_run(run, accounts.get(run["_id"])) for run in runs]

    def delete_run(self, user_id: str, run_id) -> dict:
        """Accept an owner-scoped permanent deletion for worker cleanup."""
        run = self.repository.find_owned_run(user_id, run_id)
        if run is None:
            raise NotFoundError("Backtest run not found.")
        if run.get("status") == "deleting":
            return {"id": str(run["_id"]), "status": "deleting"}
        if run.get("status") not in {"preparing", "ready"}:
            raise ConflictError("Backtest run cannot be deleted in its current state.")

        now = utc_now()
        deleting = self.repository.request_deletion(
            user_id, run["_id"], now=now
        )
        if deleting is None:
            current = self.repository.find_owned_run(user_id, run["_id"])
            if current is None:
                raise NotFoundError("Backtest run not found.")
            if current.get("status") == "deleting":
                return {"id": str(current["_id"]), "status": "deleting"}
            raise ConflictError("Backtest run changed; refresh and try again.")

        user_oid = ObjectId(user_id)
        mongo.db.trade_accounts.update_many(
            {
                "user_id": user_oid,
                "workspace_mode": "backtest",
                "$or": [
                    {"backtest_run_id": deleting["_id"]},
                    {"_id": deleting.get("account_id")},
                ],
            },
            {"$set": {"status": "deleting", "updated_at": now}},
        )
        self.job_repository.cancel_for_run(deleting["_id"], now=now)
        return {"id": str(deleting["_id"]), "status": "deleting"}

    def get_run(self, user_id: str, run_id) -> dict:
        run = self.repository.find_owned_run(user_id, run_id)
        if run is None:
            raise NotFoundError("Backtest run not found.")
        from app.backtests.schemas import serialize_run

        account = mongo.db.trade_accounts.find_one(
            {"_id": run["account_id"], "user_id": ObjectId(user_id)}
        )
        result = serialize_run(run, account)
        result["tabs"] = []
        if run["status"] == "ready":
            result["tabs"] = [
                {
                    "id": tab["id"],
                    "position": tab["position"],
                    "interval_minutes": tab["interval_minutes"],
                }
                for tab in self.repository.list_chart_tabs(user_id, run["_id"])
            ]
        return result

    def get_available_candle_dates(
        self,
        user_id: str,
        run_id,
        *,
        before: str | None = None,
        after: str | None = None,
    ) -> list[str]:
        """List UTC dates containing snapshot candles, with exclusive bounds."""
        run = self._find_ready_run(user_id, run_id)
        before_date = _parse_date(before, "before") if before is not None else None
        after_date = _parse_date(after, "after") if after is not None else None
        raw_dates = run["snapshot"].get("available_utc_dates")
        if raw_dates is None:
            # Compatibility for snapshots written before coverage metadata.
            frame = self.snapshot_store.read_snapshot(
                run["snapshot"]["object_key"]
            )
            raw_dates = [
                datetime.fromtimestamp(
                    int(time_ms) / 1000, tz=timezone.utc
                ).date()
                for time_ms in frame["time_ms"].tolist()
            ]
        available = sorted(
            {
                _stored_utc_date(value) for value in raw_dates
            }
        )
        return [
            value.isoformat()
            for value in available
            if (before_date is None or value < before_date)
            and (after_date is None or value > after_date)
        ]

    def get_candles_for_date(
        self, user_id: str, run_id, utc_date: str
    ) -> list[dict]:
        """Return the selected UTC day's actual candles from its snapshot."""
        run = self._find_ready_run(user_id, run_id)
        requested_date = _parse_date(utc_date, "date")
        day_start = datetime.combine(
            requested_date, time.min, tzinfo=timezone.utc
        )
        day_end = day_start + timedelta(days=1)
        day_start_ms = int(day_start.timestamp() * 1000)
        day_end_ms = int(day_end.timestamp() * 1000)
        if (
            day_end_ms <= int(run.get("context_start_utc_ms", run["start_utc_ms"]))
            or day_start_ms >= int(run["end_utc_ms"])
        ):
            raise ValidationError(
                "The requested UTC date is outside this run's selection."
            )

        frame = self.snapshot_store.read_snapshot_day(
            run["snapshot"], requested_date.isoformat()
        )
        frame = frame[
            (frame["time_ms"] >= day_start_ms)
            & (frame["time_ms"] < day_end_ms)
        ].sort_values("time_ms", kind="stable")
        return [
            {
                "time_ms": int(row.time_ms),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
            for row in frame.itertuples(index=False)
        ]

    def save_replay_position(
        self,
        user_id: str,
        run_id,
        *,
        source_candle_index,
        time_ms,
        expected_revision,
    ) -> dict:
        """Validate a snapshot position then atomically save its new revision."""
        run = self._find_ready_run(user_id, run_id)
        source_candle_index = _require_nonnegative_int(
            source_candle_index, "source_candle_index"
        )
        time_ms = _require_nonnegative_int(time_ms, "time_ms")
        expected_revision = _require_nonnegative_int(
            expected_revision, "expected_revision"
        )
        cursor = run.get("replay_cursor") or {}
        if cursor.get("revision") != expected_revision:
            raise ConflictError("Replay position revision is stale.")

        replay_start_index = int(
            run.get("snapshot", {}).get("replay_start_source_index", 0)
        )
        if source_candle_index < replay_start_index:
            raise ValidationError(
                "Replay position cannot precede the selected replay start."
            )

        snapshot_time = self.snapshot_store.read_snapshot_candle_time(
            run["snapshot"], source_candle_index
        )
        if snapshot_time is None or int(snapshot_time) != time_ms:
            raise ValidationError(
                "source_candle_index and time_ms must identify the same "
                "snapshot candle."
            )

        now = utc_now()
        saved = self.repository.compare_and_set_replay_cursor(
            user_id,
            run["_id"],
            expected_revision=expected_revision,
            source_candle_index=source_candle_index,
            time_ms=time_ms,
            now=now,
        )
        if saved is not None:
            return saved

        current = self.repository.find_owned_run(user_id, run["_id"])
        if current is None:
            raise NotFoundError("Backtest run not found.")
        current_cursor = current.get("replay_cursor") or {}
        if current_cursor.get("revision") != expected_revision:
            raise ConflictError("Replay position revision is stale.")
        if current.get("status") != "ready":
            raise ConflictError("Backtest run is not ready for replay.")
        raise ConflictError("Replay position changed; reload and try again.")

    def _find_ready_run(self, user_id: str, run_id) -> dict:
        run = self.repository.find_owned_run(user_id, run_id)
        if run is None:
            raise NotFoundError("Backtest run not found.")
        if run.get("status") != "ready" or not run.get("snapshot"):
            raise ConflictError("Backtest run is not ready for replay.")
        return run

    def get_chart_workspace(self, user_id: str, run_id) -> dict:
        """Load the user's saved layout or read-only legacy tab records."""
        run = self._find_ready_run(user_id, run_id)
        document = self.repository.find_chart_workspace(user_id, run["_id"])
        if document is not None:
            serialized = serialize_chart_workspace(document)
            revision = int(document["revision"])
            legacy_tabs = []
        else:
            serialized = None
            revision = 0
            legacy_tabs = [
                {
                    "id": tab["id"],
                    "position": tab["position"],
                    "interval_minutes": tab["interval_minutes"],
                }
                for tab in self.repository.list_chart_tabs(user_id, run["_id"])
            ]
        return {
            "workspace": serialized,
            "revision": revision,
            "legacy_tabs": legacy_tabs,
        }

    def save_chart_workspace(
        self,
        user_id: str,
        run_id,
        *,
        expected_revision,
        workspace,
    ) -> dict:
        """Validate and CAS-save the complete workspace for an owned run."""
        run = self._find_ready_run(user_id, run_id)
        expected_revision = _require_nonnegative_int(
            expected_revision, "expected_revision"
        )
        try:
            normalized = validate_chart_workspace(workspace, str(run["_id"]))
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        document = self.repository.compare_and_set_chart_workspace(
            user_id,
            run["_id"],
            expected_revision=expected_revision,
            workspace=normalized,
            now=utc_now(),
        )
        if document is None:
            current = self.repository.find_chart_workspace(user_id, run["_id"])
            current_revision = int(current["revision"]) if current else 0
            raise ConflictError(
                "Chart workspace revision is stale.",
                details=[{"current_revision": current_revision}],
            )

        # The legacy records remain the migration source until this successful
        # revision-zero write commits the replacement workspace.
        if expected_revision == 0:
            self.repository.delete_chart_tabs(user_id, run["_id"])

        return {
            "workspace": serialize_chart_workspace(document),
            "revision": int(document["revision"]),
            "legacy_tabs": [],
        }

    def get_drawing_state(
        self, user_id: str, run_id, interval_minutes
    ) -> dict:
        """Load drawing state scoped to the authenticated run and interval."""
        run = self._find_ready_run(user_id, run_id)
        interval = _parse_interval_minutes(interval_minutes)
        document = self.repository.find_drawing_state(
            user_id, run["_id"], interval
        )
        return serialize_drawing_state(document, interval)

    def save_drawing_state(
        self,
        user_id: str,
        run_id,
        interval_minutes,
        payload: dict,
    ) -> dict:
        """Validate and CAS-save an opaque CandleKit drawing export."""
        run = self._find_ready_run(user_id, run_id)
        interval = _parse_interval_minutes(interval_minutes)

        candlekit_version = payload.get("candlekit_version")
        if (
            not isinstance(candlekit_version, str)
            or not candlekit_version.strip()
        ):
            raise ValidationError("candlekit_version must be a nonempty string.")

        schema_version = payload.get("schema_version")
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version < 1
        ):
            raise ValidationError("schema_version must be a positive integer.")
        expected_revision = _require_nonnegative_int(
            payload.get("expected_revision"), "expected_revision"
        )
        serialized_state = payload.get("serialized_state")
        if not isinstance(serialized_state, str):
            raise ValidationError("serialized_state must be a JSON object string.")
        try:
            payload_size = len(serialized_state.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValidationError(
                "serialized_state must contain valid UTF-8 text."
            ) from exc
        if payload_size > MAX_DRAWING_STATE_BYTES:
            raise ValidationError(
                "serialized_state exceeds the 1 MiB drawing-state limit."
            )
        try:
            parsed_state = json.loads(
                serialized_state, parse_constant=_reject_json_constant
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValidationError("serialized_state must be valid JSON.") from exc
        if not isinstance(parsed_state, (dict, list)):
            raise ValidationError(
                "serialized_state must encode a JSON object or array."
            )

        now = utc_now()
        saved = self.repository.compare_and_set_drawing_state(
            user_id,
            run["_id"],
            interval_minutes=interval,
            candlekit_version=candlekit_version,
            schema_version=schema_version,
            serialized_state=serialized_state,
            expected_revision=expected_revision,
            now=now,
        )
        if saved is None:
            latest = self.repository.find_drawing_state(
                user_id, run["_id"], interval
            )
            latest_revision = latest.get("revision", 0) if latest else 0
            raise ConflictError(
                "Drawing state revision is stale.",
                details=[{"latest_revision": latest_revision}],
            )
        return serialize_drawing_state(saved, interval)

    def retry_run(self, user_id: str, run_id) -> dict:
        run = self.repository.find_owned_run(user_id, run_id)
        if run is None or run.get("status") != "preparing":
            raise NotFoundError("Backtest run not found.")
        if not self.preparation_jobs.requeue(run["_id"], now=utc_now()):
            raise ConflictError(
                "Preparation is currently leased by a worker. Retry after it "
                "finishes or its lease expires."
            )
        return self.get_run(user_id, run["_id"])

    def list_notices(self, user_id: str) -> list[dict]:
        from app.backtests.schemas import serialize_notice

        return [
            serialize_notice(item)
            for item in self.repository.list_notices(user_id)
        ]

    def dismiss_notice(self, user_id: str, notice_id) -> None:
        if not self.repository.dismiss_notice(user_id, notice_id):
            raise NotFoundError("Preparation notice not found.")
