"""Run-scoped mutation gate and recoverable simulation operation lifecycle.

This module coordinates idempotency, sequence reservation, and atomic
publication. Trading rules and deterministic document writes belong to the
effect handler supplied by the simulation engine integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import math
from typing import Any, Callable, Mapping

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.backtests.repository import BacktestRepository
from app.backtests.simulation_repository import BacktestSimulationRepository
from app.backtests.simulation_schemas import (
    OPERATION_KINDS,
    make_simulation_operation_doc,
)
from app.utils.datetime_utils import utc_now
from app.utils.errors import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)

SimulationEffectHandler = Callable[[dict, dict], Mapping[str, Any]]
SimulationCleanupHandler = Callable[[dict, dict, int], Any]


class SimulationRejected(Exception):
    """A validated command rejected by business rules before it stages effects."""

    def __init__(self, message: str, *, result: dict[str, Any] | None = None):
        super().__init__(message)
        self.result = dict(result or {})
        self.result.setdefault("message", message)


class SimulationPendingError(ConflictError):
    """The operation remains gated and must be resumed after a transient error."""

    status_code = 503


class SimulationService:
    """Serialize all run mutations through one durable CAS sequence.

    ``effect_handler`` receives ``(operation, run)`` and returns a mapping with
    ``result`` and ``run_updates``. Its inserts must use stable ids so replaying
    the same pending operation is safe. A reset handler returns the new cursor;
    physical removal is performed by ``cleanup_handler`` after the generation
    change is committed.
    """

    def __init__(
        self,
        backtest_repository: BacktestRepository | None = None,
        simulation_repository: BacktestSimulationRepository | None = None,
        *,
        effect_handler: SimulationEffectHandler | None = None,
        cleanup_handler: SimulationCleanupHandler | None = None,
    ) -> None:
        self.backtest_repository = backtest_repository or BacktestRepository()
        self.simulation_repository = (
            simulation_repository or BacktestSimulationRepository()
        )
        self.effect_handler = effect_handler
        self.cleanup_handler = cleanup_handler

    def execute_operation(
        self,
        user_id: str,
        run_id,
        *,
        client_operation_id: str,
        expected_revision: int,
        kind: str,
        request: Mapping[str, Any],
        effect_handler: SimulationEffectHandler | None = None,
        cleanup_handler: SimulationCleanupHandler | None = None,
    ) -> dict[str, Any]:
        """Run or replay one owner-scoped simulation mutation.

        The request mapping is the already validated command body. The service
        adds ``expected_revision`` to the persisted comparison payload and
        removes ``client_operation_id`` because that key is stored separately.
        """
        self._validate_command(
            client_operation_id, expected_revision, kind, request
        )
        handler = effect_handler or self.effect_handler
        cleanup = cleanup_handler or self.cleanup_handler
        payload = dict(request)
        payload.pop("client_operation_id", None)
        payload["expected_revision"] = expected_revision

        existing = self.simulation_repository.find_operation_by_key(
            user_id, run_id, client_operation_id
        )
        if existing is not None:
            self._assert_same_request(existing, kind, payload)
            return self._resume_or_return(
                user_id,
                run_id,
                existing,
                effect_handler=handler,
                cleanup_handler=cleanup,
            )

        run = self.backtest_repository.find_owned_run(user_id, run_id)
        self._require_mutable_run(run, kind)
        run = self.backtest_repository.ensure_simulation_control(user_id, run_id)
        self._require_mutable_run(run, kind)
        control = self._control(run)
        if expected_revision != control["control_revision"]:
            raise ConflictError("Simulation control revision is stale.")
        if control.get("pending_operation_id") is not None:
            raise ConflictError("Another simulation operation is still pending.")
        if kind == "rewind" and control.get("has_accepted_order"):
            raise ConflictError("Reset is required before moving backward.")

        sequence = control["committed_sequence"] + 1
        operation_id = ObjectId()
        operation = make_simulation_operation_doc(
            user_id=run["user_id"],
            run_id=run["_id"],
            client_operation_id=client_operation_id,
            sequence=sequence,
            control_revision=expected_revision + 1,
            reset_generation=control["reset_generation"],
            kind=kind,
            request=payload,
            created_at=utc_now(),
            operation_id=operation_id,
        )
        try:
            self.simulation_repository.insert_operation(operation)
        except DuplicateKeyError:
            # The idempotency key may have been inserted by a concurrent retry,
            # or another key may have reserved this sequence first.
            existing = self.simulation_repository.find_operation_by_key(
                user_id, run_id, client_operation_id
            )
            if existing is not None:
                self._assert_same_request(existing, kind, payload)
                return self._resume_or_return(
                    user_id,
                    run_id,
                    existing,
                    effect_handler=handler,
                    cleanup_handler=cleanup,
                )
            raise ConflictError("Simulation operation sequence changed; retry.")

        reserved = self.backtest_repository.reserve_simulation_operation(
            user_id,
            run_id,
            operation_id=operation_id,
            kind=kind,
            sequence=sequence,
            reset_generation=control["reset_generation"],
            expected_revision=expected_revision,
        )
        if reserved is None:
            # Same-key callers can race after the first one reserves the gate.
            # If that happened, continue the journal record rather than treating
            # it as a conflicting second command.
            latest = self.simulation_repository.find_operation_by_key(
                user_id, run_id, client_operation_id
            )
            current_run = self.backtest_repository.find_owned_run(user_id, run_id)
            if latest is not None and current_run is not None:
                pending_id = self._control(current_run).get(
                    "pending_operation_id"
                )
                if self._same_id(pending_id, latest.get("_id")):
                    return self._resume_or_return(
                        user_id,
                        run_id,
                        latest,
                        effect_handler=handler,
                        cleanup_handler=cleanup,
                    )
                if (
                    self._control(current_run)["committed_sequence"]
                    >= latest["sequence"]
                ):
                    return self._resume_or_return(
                        user_id,
                        run_id,
                        latest,
                        effect_handler=handler,
                        cleanup_handler=cleanup,
                    )
            self.simulation_repository.delete_unclaimed_operation(
                user_id, run_id, operation_id
            )
            self._raise_current_conflict(user_id, run_id, kind)

        return self._continue_pending(
            user_id,
            run_id,
            operation,
            reserved,
            effect_handler=handler,
            cleanup_handler=cleanup,
        )

    def resume_pending_operation(
        self,
        user_id: str,
        run_id,
        operation_id,
        *,
        effect_handler: SimulationEffectHandler | None = None,
        cleanup_handler: SimulationCleanupHandler | None = None,
    ) -> dict[str, Any]:
        """Resume one explicitly selected pending operation within its owner."""
        operation = self.simulation_repository.find_operation_by_id(
            user_id, run_id, operation_id
        )
        if operation is None:
            raise NotFoundError("Simulation operation not found.")
        if operation.get("state") in {"committed", "rejected"}:
            return self._response(operation)
        return self._resume_or_return(
            user_id,
            run_id,
            operation,
            effect_handler=effect_handler or self.effect_handler,
            cleanup_handler=cleanup_handler or self.cleanup_handler,
        )

    def resume_pending_operations(
        self,
        *,
        limit: int = 100,
        effect_handler: SimulationEffectHandler | None = None,
        cleanup_handler: SimulationCleanupHandler | None = None,
    ) -> dict[str, Any]:
        """Worker entry point for pending effects and reset cleanup recovery."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        handler = effect_handler or self.effect_handler
        cleanup = cleanup_handler or self.cleanup_handler
        completed = 0
        pending = 0
        failures: list[dict[str, str]] = []
        for operation in self.simulation_repository.list_recoverable_operations(
            limit=limit
        ):
            user_id = operation.get("user_id")
            run_id = operation.get("run_id")
            operation_id = operation.get("_id")
            if user_id is None or run_id is None or operation_id is None:
                failures.append(
                    {
                        "operation_id": str(operation_id),
                        "error": "Invalid journal scope.",
                    }
                )
                continue
            try:
                response = self.resume_pending_operation(
                    str(user_id),
                    run_id,
                    operation_id,
                    effect_handler=handler,
                    cleanup_handler=cleanup,
                )
            except Exception as exc:  # Recovery must not starve later operations.
                pending += 1
                logger.exception(
                    "Unable to resume Backtest simulation operation %s",
                    operation_id,
                )
                failures.append(
                    {"operation_id": str(operation_id), "error": str(exc)}
                )
                continue
            if response.get("state") in {"committed", "rejected"}:
                completed += 1
            else:
                pending += 1
        return {"completed": completed, "pending": pending, "failures": failures}

    @staticmethod
    def _validate_command(
        client_operation_id: str,
        expected_revision: int,
        kind: str,
        request: Mapping[str, Any],
    ) -> None:
        if (
            not isinstance(client_operation_id, str)
            or not client_operation_id.strip()
            or len(client_operation_id) > 128
        ):
            raise ValidationError(
                "client_operation_id must contain 1 to 128 characters."
            )
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise ValidationError("expected_revision must be a nonnegative integer.")
        if not isinstance(kind, str):
            raise ValidationError("Simulation operation kind is invalid.")
        if kind not in OPERATION_KINDS:
            raise ValidationError("Simulation operation kind is unsupported.")
        if not isinstance(request, Mapping):
            raise ValidationError("Simulation request must be an object.")

    @staticmethod
    def _require_mutable_run(run: dict | None, kind: str) -> None:
        if run is None:
            raise NotFoundError("Backtest run not found.")
        status = run.get("status")
        if status == "deleting":
            raise ConflictError("Backtest run is being deleted.")
        if status == "complete" and kind != "reset":
            raise ConflictError("Completed runs must be reset before mutation.")
        if status not in {"ready", "complete"}:
            raise ConflictError("Backtest run is not ready for simulation.")

    def _require_effect_handler(
        self, handler: SimulationEffectHandler | None, operation: dict
    ) -> SimulationEffectHandler:
        if handler is None:
            raise SimulationPendingError(
                "Simulation operation "
                f"{operation.get('_id')} is pending and needs a worker handler."
            )
        return handler

    @staticmethod
    def _control(run: dict) -> dict[str, Any]:
        raw = run.get("simulation_control")
        if not isinstance(raw, dict):
            raise ConflictError("Simulation control state is unavailable.")
        control = dict(raw)
        for name in ("committed_sequence", "control_revision", "reset_generation"):
            value = control.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ConflictError("Simulation control state is invalid.")
        control.setdefault("has_accepted_order", False)
        control.setdefault("pending_operation_id", None)
        return control

    def _resume_or_return(
        self,
        user_id: str,
        run_id,
        operation: dict,
        *,
        effect_handler: SimulationEffectHandler | None,
        cleanup_handler: SimulationCleanupHandler | None,
    ) -> dict[str, Any]:
        if operation.get("state") in {"committed", "rejected"}:
            return self._response(operation)
        run = self.backtest_repository.find_owned_run(user_id, run_id)
        if run is None:
            raise NotFoundError("Backtest run not found.")
        run = self.backtest_repository.ensure_simulation_control(user_id, run_id)
        if run is None:
            raise NotFoundError("Backtest run not found.")
        control = self._control(run)
        operation_id = operation["_id"]

        if operation.get("state") == "cleanup_pending":
            return self._finish_reset(
                user_id, run_id, operation, run, cleanup_handler
            )

        if control["committed_sequence"] >= operation["sequence"]:
            # A crash can occur after the run CAS and before journal finalization.
            return self._recover_committed(
                user_id, run_id, operation, run, cleanup_handler
            )

        if not self._same_id(
            control.get("pending_operation_id"), operation_id
        ):
            if control.get("pending_operation_id") is not None:
                raise ConflictError("Another simulation operation is pending.")
            if (
                operation["sequence"] != control["committed_sequence"] + 1
                or operation["control_revision"] - 1
                != control["control_revision"]
                or operation["reset_generation"] != control["reset_generation"]
            ):
                raise ConflictError(
                    "Simulation operation cannot be resumed at this revision."
                )
            reserved = self.backtest_repository.reserve_simulation_operation(
                user_id,
                run_id,
                operation_id=operation_id,
                kind=operation["kind"],
                sequence=operation["sequence"],
                reset_generation=operation["reset_generation"],
                expected_revision=operation["control_revision"] - 1,
            )
            if reserved is None:
                raise ConflictError(
                    "Simulation operation could not claim its run gate."
                )
            run = reserved

        return self._continue_pending(
            user_id,
            run_id,
            operation,
            run,
            effect_handler=effect_handler,
            cleanup_handler=cleanup_handler,
        )

    def _continue_pending(
        self,
        user_id: str,
        run_id,
        operation: dict,
        run: dict,
        *,
        effect_handler: SimulationEffectHandler | None,
        cleanup_handler: SimulationCleanupHandler | None,
    ) -> dict[str, Any]:
        operation = self.simulation_repository.find_operation_by_id(
            user_id, run_id, operation["_id"]
        ) or operation
        if operation.get("final_state") is None:
            handler = self._require_effect_handler(effect_handler, operation)
            try:
                output = handler(operation, run)
                if not isinstance(output, Mapping):
                    raise TypeError("Simulation effect handler must return a mapping.")
                result = output.get("result") or {}
                run_updates = output.get("run_updates") or {}
                if not isinstance(result, Mapping) or not isinstance(
                    run_updates, Mapping
                ):
                    raise TypeError("Handler result and run_updates must be mappings.")
                result = dict(result)
                run_updates = self._prepare_run_updates(
                    operation, run, dict(run_updates)
                )
                final_state = "committed"
            except SimulationRejected as exc:
                result = dict(exc.result)
                final_state = "rejected"
                run_updates = {}
            except Exception as exc:
                logger.exception(
                    "Simulation effect failed for operation %s",
                    operation.get("_id"),
                )
                raise SimulationPendingError(
                    f"Simulation operation {operation['_id']} remains pending "
                    "and can be retried."
                ) from exc

            persisted = self.simulation_repository.update_operation(
                user_id,
                run_id,
                operation["_id"],
                {
                    "final_state": final_state,
                    "result": result,
                    "commit_updates": run_updates,
                },
                states=("pending",),
            )
            if not persisted:
                latest = self.simulation_repository.find_operation_by_id(
                    user_id, run_id, operation["_id"]
                )
                if latest is None or latest.get("final_state") is None:
                    raise SimulationPendingError(
                        f"Simulation operation {operation['_id']} could not "
                        "checkpoint its result."
                    )
                operation = latest
            else:
                operation = {
                    **operation,
                    "final_state": final_state,
                    "result": result,
                    "commit_updates": run_updates,
                }

        if operation["kind"] == "reset" and operation["final_state"] == "committed":
            return self._apply_reset(
                user_id,
                run_id,
                operation,
                run,
                cleanup_handler,
            )

        run_updates = operation.get("commit_updates") or {}
        committed = self.backtest_repository.commit_simulation_operation(
            user_id,
            run_id,
            operation_id=operation["_id"],
            sequence=operation["sequence"],
            reset_generation=operation["reset_generation"],
            control_revision=operation["control_revision"],
            run_updates=run_updates,
            accepted_order=(
                operation["kind"] == "submit_order"
                and operation["final_state"] == "committed"
            ),
            allow_complete=operation["kind"] == "reset",
        )
        if not committed:
            run_now = self.backtest_repository.find_owned_run(user_id, run_id)
            if (
                run_now is not None
                and self._control(run_now)["committed_sequence"]
                >= operation["sequence"]
            ):
                return self._recover_committed(
                    user_id, run_id, operation, run_now, cleanup_handler
                )
            raise SimulationPendingError(
                f"Simulation operation {operation['_id']} remains pending "
                "at the run gate."
            )
        self._publish_committed_effects(operation)
        operation = self._mark_terminal(operation)
        return self._response(operation)

    def _apply_reset(
        self,
        user_id: str,
        run_id,
        operation: dict,
        run: dict,
        cleanup_handler: SimulationCleanupHandler | None,
    ) -> dict[str, Any]:
        updates = dict(operation.get("commit_updates") or {})
        updates["status"] = "ready"
        updates["current_balance_usd"] = run.get(
            "initial_balance_usd", run.get("current_balance_usd", 0.0)
        )
        # Hide old-generation Journal rows before advancing the run's
        # generation. If the process stops after the reset CAS, recovery sees
        # an already-hidden generation while it resumes physical cleanup.
        self.simulation_repository.hide_generation_publications(
            user_id,
            run_id,
            reset_generation=operation["reset_generation"],
        )
        started = self.backtest_repository.begin_simulation_reset(
            user_id,
            run_id,
            operation_id=operation["_id"],
            sequence=operation["sequence"],
            previous_generation=operation["reset_generation"],
            control_revision=operation["control_revision"],
            run_updates=updates,
        )
        if not started:
            run_now = self.backtest_repository.find_owned_run(user_id, run_id)
            if run_now is None:
                raise NotFoundError("Backtest run not found.")
            control = self._control(run_now)
            if not (
                control["committed_sequence"] == operation["sequence"]
                and control["reset_generation"] == operation["reset_generation"] + 1
            ):
                raise SimulationPendingError(
                    f"Reset operation {operation['_id']} remains pending "
                    "at the run gate."
                )
            run = run_now
        else:
            run = self.backtest_repository.find_owned_run(user_id, run_id) or run

        self.simulation_repository.update_operation(
            user_id,
            run_id,
            operation["_id"],
            {"state": "cleanup_pending"},
            states=("pending", "cleanup_pending"),
        )
        operation = {
            **operation,
            "state": "cleanup_pending",
            "final_state": "committed",
        }
        return self._finish_reset(
            user_id, run_id, operation, run, cleanup_handler
        )

    def _finish_reset(
        self,
        user_id: str,
        run_id,
        operation: dict,
        run: dict,
        cleanup_handler: SimulationCleanupHandler | None,
    ) -> dict[str, Any]:
        if operation.get("kind") != "reset":
            raise ConflictError("Only reset operations can enter cleanup.")
        expected_generation = operation["reset_generation"] + 1
        control = self._control(run)
        if not (
            control["committed_sequence"] == operation["sequence"]
            and control["reset_generation"] == expected_generation
        ):
            raise SimulationPendingError("Reset generation has not been committed yet.")
        try:
            self.simulation_repository.hide_generation_publications(
                user_id,
                run_id,
                reset_generation=operation["reset_generation"],
            )
            # Trades are published through the shared Trades collections. Use
            # the normal cascade before deleting generation fills so executions
            # and media linked to each simulated trade cannot be orphaned.
            from app.trades.service import TradeService

            TradeService().delete_backtest_simulation_trades(
                user_id,
                run_id,
                reset_generation=operation["reset_generation"],
            )
            if cleanup_handler is not None:
                cleanup_handler(operation, run, operation["reset_generation"])
            else:
                self.simulation_repository.delete_generation_data(
                    user_id, run_id, operation["reset_generation"]
                )
        except Exception as exc:
            raise SimulationPendingError(
                f"Reset operation {operation['_id']} cleanup remains pending."
            ) from exc

        released = self.backtest_repository.finish_simulation_reset(
            user_id,
            run_id,
            operation_id=operation["_id"],
            sequence=operation["sequence"],
            reset_generation=expected_generation,
        )
        if not released:
            latest_run = self.backtest_repository.find_owned_run(user_id, run_id)
            if latest_run is None:
                raise NotFoundError("Backtest run not found.")
            latest_control = self._control(latest_run)
            if (
                latest_control["committed_sequence"] != operation["sequence"]
                or latest_control["reset_generation"] != expected_generation
                or latest_control.get("pending_operation_id") is not None
            ):
                raise SimulationPendingError(
                    "Reset cleanup is complete but its gate remains pending."
                )
        operation = self._mark_terminal(
            {
                **operation,
                "final_state": "committed",
                "result": operation.get("result") or {},
            }
        )
        return self._response(operation)

    def _recover_committed(
        self,
        user_id: str,
        run_id,
        operation: dict,
        run: dict,
        cleanup_handler: SimulationCleanupHandler | None,
    ) -> dict[str, Any]:
        control = self._control(run)
        if operation["kind"] == "reset":
            expected_generation = operation["reset_generation"] + 1
            if control["reset_generation"] != expected_generation:
                raise ConflictError(
                    "Reset journal does not match the committed generation."
                )
            if operation.get("state") != "cleanup_pending":
                self.simulation_repository.update_operation(
                    user_id,
                    run_id,
                    operation["_id"],
                    {"state": "cleanup_pending"},
                    states=("pending",),
                )
                operation = {**operation, "state": "cleanup_pending"}
            if control.get("pending_operation_id") is None:
                operation = self._mark_terminal(
                    {**operation, "final_state": "committed"}
                )
                return self._response(operation)
            return self._finish_reset(
                user_id, run_id, operation, run, cleanup_handler
            )
        final_state = operation.get("final_state") or "committed"
        if final_state == "committed":
            self._publish_committed_effects(operation, run=run)
        return self._response(
            self._mark_terminal({**operation, "final_state": final_state})
        )

    def _publish_committed_effects(
        self, operation: dict, *, run: dict | None = None
    ) -> None:
        """Publish staged shared-collection rows only after the run CAS."""
        if operation.get("final_state") == "rejected":
            return
        if run is None:
            run = self.backtest_repository.find_owned_run(
                str(operation["user_id"]), operation["run_id"]
            )
        if run is None:
            # A concurrently completed reset/deletion may already have removed
            # this generation; it cannot be published as current Journal data.
            return
        control = self._control(run)
        if (
            control["committed_sequence"] < operation["sequence"]
            or control["reset_generation"] != operation["reset_generation"]
        ):
            return
        try:
            self.simulation_repository.publish_committed_effects(
                operation["user_id"],
                operation["run_id"],
                reset_generation=operation["reset_generation"],
                operation_sequence=operation["sequence"],
            )
        except Exception as exc:
            raise SimulationPendingError(
                f"Simulation operation {operation['_id']} committed but its "
                "Journal records remain pending publication."
            ) from exc

    def _mark_terminal(self, operation: dict) -> dict:
        final_state = operation.get("final_state") or "committed"
        updated = self.simulation_repository.update_operation(
            operation["user_id"],
            operation["run_id"],
            operation["_id"],
            {"state": final_state, "committed_at": utc_now()},
            states=("pending", "cleanup_pending", final_state),
        )
        if updated:
            return {**operation, "state": final_state, "committed_at": utc_now()}
        latest = self.simulation_repository.find_operation_by_id(
            operation["user_id"], operation["run_id"], operation["_id"]
        )
        if latest is None:
            raise SimulationPendingError(
                "Committed operation journal record is missing."
            )
        return latest

    def _prepare_run_updates(
        self, operation: dict, run: dict, updates: dict[str, Any]
    ) -> dict[str, Any]:
        allowed = {
            "replay_cursor",
            "current_balance_usd",
            "simulation_risk_percent",
            "status",
        }
        if not set(updates).issubset(allowed):
            raise ValueError("Simulation handler returned unsupported run updates.")
        if "status" in updates:
            if operation["kind"] != "advance" or updates["status"] != "complete":
                raise ValueError("Only final-candle advance may complete a run.")
        if "current_balance_usd" in updates:
            balance = updates["current_balance_usd"]
            if (
                isinstance(balance, bool)
                or not isinstance(balance, (float, int))
                or not math.isfinite(balance)
            ):
                raise ValueError("current_balance_usd must be finite.")
            updates["current_balance_usd"] = float(balance)
        if "simulation_risk_percent" in updates:
            risk_percent = updates["simulation_risk_percent"]
            if (
                operation["kind"] != "update_risk"
                or isinstance(risk_percent, bool)
                or not isinstance(risk_percent, (float, int))
                or not math.isfinite(risk_percent)
                or risk_percent <= 0
                or risk_percent > 100
            ):
                raise ValueError(
                    "simulation_risk_percent must be greater than 0 and no more than 100."
                )
            updates["simulation_risk_percent"] = float(risk_percent)
        if operation["kind"] in {"advance", "rewind", "reset"}:
            raw_cursor = updates.get("replay_cursor")
            if not isinstance(raw_cursor, Mapping):
                raise ValueError("Cursor operations must return replay_cursor.")
            index = raw_cursor.get("source_candle_index")
            time_ms = raw_cursor.get("time_ms")
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or isinstance(time_ms, bool)
                or not isinstance(time_ms, int)
                or time_ms < 0
            ):
                raise ValueError("Handler returned an invalid replay cursor.")
            current_cursor = run.get("replay_cursor") or {}
            current_index = current_cursor.get("source_candle_index")
            if (
                operation["kind"] == "advance"
                and isinstance(current_index, int)
                and index <= current_index
            ):
                raise ValueError("Advance cursor must move forward.")
            if (
                operation["kind"] == "rewind"
                and isinstance(current_index, int)
                and index >= current_index
            ):
                raise ValueError("Rewind cursor must move backward.")
            updates["replay_cursor"] = {
                "source_candle_index": index,
                "time_ms": time_ms,
                "revision": int(current_cursor.get("revision", -1)) + 1,
                "updated_at": utc_now(),
            }
        if operation["kind"] == "reset":
            updates["status"] = "ready"
            updates["current_balance_usd"] = float(
                run.get("initial_balance_usd", run.get("current_balance_usd", 0.0))
            )
        return updates

    def _raise_current_conflict(self, user_id: str, run_id, kind: str) -> None:
        run = self.backtest_repository.find_owned_run(user_id, run_id)
        self._require_mutable_run(run, kind)
        control = self._control(run)
        if control.get("pending_operation_id") is not None:
            raise ConflictError("Another simulation operation is still pending.")
        if kind == "rewind" and control.get("has_accepted_order"):
            raise ConflictError("Reset is required before moving backward.")
        raise ConflictError("Simulation control revision is stale.")

    @staticmethod
    def _assert_same_request(operation: dict, kind: str, request: dict) -> None:
        if operation.get("kind") != kind or SimulationService._canonical(
            operation.get("request") or {}
        ) != SimulationService._canonical(request):
            raise ConflictError(
                "client_operation_id was already used for a different request."
            )

    @staticmethod
    def _canonical(value: Any) -> str:
        def convert(item):
            if isinstance(item, ObjectId):
                return str(item)
            if isinstance(item, datetime):
                normalized = item
                if normalized.tzinfo is None:
                    normalized = normalized.replace(tzinfo=timezone.utc)
                return normalized.astimezone(timezone.utc).isoformat()
            if isinstance(item, Decimal):
                return str(item)
            if isinstance(item, Mapping):
                return {str(key): convert(child) for key, child in item.items()}
            if isinstance(item, (list, tuple)):
                return [convert(child) for child in item]
            return item

        return json.dumps(
            convert(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        )

    @staticmethod
    def _same_id(left, right) -> bool:
        if left is None or right is None:
            return left is right
        try:
            return ObjectId(left) == ObjectId(right)
        except (TypeError, ValueError):
            return left == right

    @staticmethod
    def _response(operation: dict) -> dict[str, Any]:
        return {
            "client_operation_id": operation["client_operation_id"],
            "sequence": operation["sequence"],
            "state": operation["state"],
            "control_revision": operation["control_revision"],
            "result": operation.get("result"),
        }
