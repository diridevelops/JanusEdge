"""Run-level simulation operation gate, retries, and reset recovery tests."""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.backtests.simulation_repository import BacktestSimulationRepository
from app.backtests.simulation_service import (
    SimulationPendingError,
    SimulationService,
)
from app.extensions import mongo
from app.utils.errors import ConflictError


def _seed_run(*, status="ready", sequence=0, revision=0, generation=0):
    user_id, run_id = ObjectId(), ObjectId()
    mongo.db.backtest_runs.insert_one(
        {
            "_id": run_id,
            "user_id": user_id,
            "status": status,
            "initial_balance_usd": 10_000.0,
            "current_balance_usd": 10_000.0,
            "replay_cursor": {
                "source_candle_index": 10,
                "time_ms": 1_000,
                "revision": 2,
            },
            "simulation_control": {
                "committed_sequence": sequence,
                "control_revision": revision,
                "reset_generation": generation,
                "has_accepted_order": False,
                "pending_operation_id": None,
            },
        }
    )
    return str(user_id), run_id


def _service():
    return SimulationService(
        simulation_repository=BacktestSimulationRepository()
    )


def test_worker_recovery_uses_the_effects_apply_and_cleanup_handlers(
    app, monkeypatch
):
    from app.backtests.worker import BacktestWorker
    import app.backtests.simulation_effects as effects_module
    import app.backtests.simulation_service as service_module

    with app.app_context():
        user_id, run_id = _seed_run()
        mongo.db.backtest_simulation_operations.insert_one(
            {
                "user_id": ObjectId(user_id),
                "run_id": run_id,
                "client_operation_id": "worker-recovery",
                "sequence": 1,
                "state": "pending",
            }
        )

        class Effects:
            def __init__(self, simulation_repository):
                self.simulation_repository = simulation_repository

            def apply_operation(self, operation, run):
                raise AssertionError("patched service should not execute effects")

            def cleanup_generation(self, operation, run, generation):
                raise AssertionError("patched service should not clean a generation")

        class Service:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def resume_pending_operations(self, *, limit):
                assert limit == 100
                assert callable(self.kwargs["effect_handler"])
                assert callable(self.kwargs["cleanup_handler"])
                return {"completed": 1, "pending": 0, "failures": []}

        monkeypatch.setattr(effects_module, "BacktestSimulationEffects", Effects)
        monkeypatch.setattr(service_module, "SimulationService", Service)

        assert BacktestWorker()._recover_simulation_operations() is True


def _execute(
    service,
    user_id,
    run_id,
    *,
    key,
    revision,
    request,
    kind="update_costs",
    handler,
    cleanup_handler=None,
):
    return service.execute_operation(
        user_id,
        run_id,
        client_operation_id=key,
        expected_revision=revision,
        kind=kind,
        request=request,
        effect_handler=handler,
        cleanup_handler=cleanup_handler,
    )


def test_identical_retry_returns_saved_result_and_key_reuse_conflicts(app):
    with app.app_context():
        user_id, run_id = _seed_run()
        service = _service()
        calls = []

        def handler(operation, run):
            calls.append(operation["_id"])
            return {"result": {"revision": 1, "saved": True}}

        request = {"total_spread_pips": 0.8}
        first = _execute(
            service,
            user_id,
            run_id,
            key="cost-key",
            revision=0,
            request=request,
            handler=handler,
        )
        retry = _execute(
            service,
            user_id,
            run_id,
            key="cost-key",
            revision=0,
            request=request,
            handler=handler,
        )

        assert first == retry
        assert first["state"] == "committed"
        assert first["sequence"] == 1
        assert first["control_revision"] == 1
        assert len(calls) == 1
        with pytest.raises(ConflictError, match="different request"):
            _execute(
                service,
                user_id,
                run_id,
                key="cost-key",
                revision=0,
                request={"total_spread_pips": 1.2},
                handler=handler,
            )


def test_stale_control_revision_does_not_create_second_operation(app):
    with app.app_context():
        user_id, run_id = _seed_run()
        service = _service()
        handler = lambda operation, run: {"result": {"ok": True}}
        _execute(
            service,
            user_id,
            run_id,
            key="first",
            revision=0,
            request={"total_spread_pips": 0.0},
            handler=handler,
        )

        with pytest.raises(ConflictError, match="stale"):
            _execute(
                service,
                user_id,
                run_id,
                key="stale",
                revision=0,
                request={"total_spread_pips": 0.1},
                handler=handler,
            )
        assert mongo.db.backtest_simulation_operations.count_documents(
            {"user_id": ObjectId(user_id), "run_id": run_id}
        ) == 1


def test_staged_fills_and_closed_trades_publish_only_after_sequence_commit(app):
    from app.repositories.execution_repo import ExecutionRepository
    from app.repositories.trade_repo import TradeRepository

    with app.app_context():
        user_id, run_id = _seed_run()
        user_oid = ObjectId(user_id)
        trade_id = ObjectId()
        fill_id = ObjectId()
        account_id = ObjectId()
        trades = TradeRepository()
        executions = ExecutionRepository()

        def handler(operation, _run):
            sequence = operation["sequence"]
            generation = operation["reset_generation"]
            mongo.db.trades.insert_one(
                {
                    "_id": trade_id,
                    "user_id": user_oid,
                    "trade_account_id": account_id,
                    "backtest_run_id": run_id,
                    "simulation_generation": generation,
                    "simulation_operation_sequence": sequence,
                    "status": "deleted",
                    "symbol": "EURUSD",
                }
            )
            mongo.db.executions.insert_one(
                {
                    "_id": fill_id,
                    "user_id": user_oid,
                    "trade_account_id": account_id,
                    "trade_id": trade_id,
                    "backtest_run_id": run_id,
                    "backtest_order_id": ObjectId(),
                    "reset_generation": generation,
                    "simulation_operation_sequence": sequence,
                    "simulation_committed": False,
                }
            )

            # The shared Journal repositories must not expose effects before
            # the run-level sequence CAS has completed.
            assert trades.find_by_user(user_id) == []
            assert executions.find_by_user(user_id) == []
            return {"result": {"closed": True}}

        response = _execute(
            _service(),
            user_id,
            run_id,
            key="publish-closed-position",
            revision=0,
            request={"position_id": str(ObjectId())},
            kind="close_position",
            handler=handler,
        )

        assert response["state"] == "committed"
        visible_trade = trades.find_by_user(user_id)
        visible_fill = executions.find_by_user(user_id)
        assert [trade["_id"] for trade in visible_trade] == [trade_id]
        assert visible_trade[0]["status"] == "closed"
        assert [fill["_id"] for fill in visible_fill] == [fill_id]
        assert visible_fill[0]["simulation_committed"] is True


def test_pending_operation_replays_idempotent_effects_then_commits(app):
    with app.app_context():
        user_id, run_id = _seed_run()
        service = _service()
        effects = {}
        attempts = {"count": 0}

        def interrupted_handler(operation, run):
            effects.setdefault(str(operation["_id"]), {"writes": 1})
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("simulated crash after deterministic write")
            return {
                "result": {"effect_id": str(operation["_id"])},
                "run_updates": {
                    "replay_cursor": {
                        "source_candle_index": 11,
                        "time_ms": 2_000,
                    }
                },
            }

        with pytest.raises(SimulationPendingError):
            _execute(
                service,
                user_id,
                run_id,
                key="pending-op",
                revision=0,
                request={"target_source_index": 11},
                kind="advance",
                handler=interrupted_handler,
            )

        operation = BacktestSimulationRepository().find_operation_by_key(
            user_id, run_id, "pending-op"
        )
        assert operation["state"] == "pending"
        assert mongo.db.backtest_runs.find_one({"_id": run_id})[
            "simulation_control"
        ]["pending_operation_id"] == operation["_id"]

        # The handler can be re-run for the same durable operation id. Its
        # deterministic side effect is not duplicated, then the run CAS commits.
        response = service.resume_pending_operation(
            user_id,
            run_id,
            operation["_id"],
            effect_handler=interrupted_handler,
        )
        run = mongo.db.backtest_runs.find_one({"_id": run_id})
        assert response["state"] == "committed"
        assert response["sequence"] == 1
        assert len(effects) == 1
        assert run["simulation_control"]["committed_sequence"] == 1
        assert run["simulation_control"]["pending_operation_id"] is None


def test_reset_changes_generation_and_keeps_mutations_fenced_until_cleanup(app):
    with app.app_context():
        user_id, run_id = _seed_run(
            status="complete", sequence=3, revision=3, generation=0
        )
        repository = BacktestSimulationRepository()
        order_id = ObjectId()
        repository.insert_order_version(
            {
                "user_id": ObjectId(user_id),
                "run_id": run_id,
                "reset_generation": 0,
                "order_id": order_id,
                "operation_sequence": 3,
                "entity_version": 1,
                "status": "filled",
            }
        )
        repository.insert_cost_profile(
            {
                "user_id": ObjectId(user_id),
                "run_id": run_id,
                "revision": 2,
                "operation_sequence": 2,
                "total_spread_pips": 0.7,
                "slippage_pips": 0.2,
                "commission_usd_per_lot_per_side": 4.0,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        user_oid = ObjectId(user_id)
        other_run_id = ObjectId()
        category_id = ObjectId()
        stop_moved_tag_id = ObjectId()
        mongo.db.tag_categories.insert_one(
            {
                "_id": category_id,
                "user_id": user_oid,
                "name": "General",
                "system_key": "general",
            }
        )
        mongo.db.tags.insert_one(
            {
                "_id": stop_moved_tag_id,
                "user_id": user_oid,
                "name": "stop-moved",
                "category_id": category_id,
            }
        )
        old_generation_trade_id = ObjectId()
        mongo.db.trades.insert_one(
            {
                "_id": old_generation_trade_id,
                "user_id": user_oid,
                "backtest_run_id": run_id,
                "simulation_generation": 0,
                "trade_account_id": ObjectId(),
                "import_batch_id": None,
                "status": "closed",
                "tag_ids": [stop_moved_tag_id],
            }
        )
        old_generation_execution_id = ObjectId()
        mongo.db.executions.insert_one(
            {
                "_id": old_generation_execution_id,
                "user_id": user_oid,
                "trade_id": old_generation_trade_id,
                "backtest_run_id": run_id,
                "reset_generation": 0,
                "backtest_order_id": order_id,
            }
        )
        other_run_trade_id = ObjectId()
        mongo.db.trades.insert_one(
            {
                "_id": other_run_trade_id,
                "user_id": user_oid,
                "backtest_run_id": other_run_id,
                "simulation_generation": 0,
                "trade_account_id": ObjectId(),
                "import_batch_id": None,
                "status": "closed",
                "tag_ids": [stop_moved_tag_id],
            }
        )
        service = _service()
        reset_handler = lambda operation, run: {
            "result": {"reset": True},
            "run_updates": {
                "replay_cursor": {"source_candle_index": 4, "time_ms": 4_000}
            },
        }

        def fail_cleanup(operation, run, old_generation):
            raise RuntimeError("cleanup interrupted")

        with pytest.raises(SimulationPendingError, match="cleanup remains pending"):
            _execute(
                service,
                user_id,
                run_id,
                key="reset-key",
                revision=3,
                request={"confirmed": True},
                kind="reset",
                handler=reset_handler,
                cleanup_handler=fail_cleanup,
            )

        run = mongo.db.backtest_runs.find_one({"_id": run_id})
        control = run["simulation_control"]
        assert run["status"] == "ready"
        assert control["committed_sequence"] == 4
        assert control["reset_generation"] == 1
        assert control["pending_operation_id"] is not None
        assert run["current_balance_usd"] == run["initial_balance_usd"]
        assert run["replay_cursor"]["source_candle_index"] == 4
        assert mongo.db.trades.find_one({"_id": old_generation_trade_id}) is None
        assert mongo.db.executions.find_one(
            {"_id": old_generation_execution_id}
        ) is None
        assert mongo.db.trades.find_one({"_id": other_run_trade_id})["tag_ids"] == [
            stop_moved_tag_id
        ]
        assert mongo.db.tags.find_one({"_id": stop_moved_tag_id}) is not None
        assert mongo.db.tag_categories.find_one({"_id": category_id}) is not None

        new_generation_trade_id = ObjectId()
        mongo.db.trades.insert_one(
            {
                "_id": new_generation_trade_id,
                "user_id": user_oid,
                "backtest_run_id": run_id,
                "simulation_generation": 1,
                "trade_account_id": ObjectId(),
                "import_batch_id": None,
                "status": "closed",
                "tag_ids": [stop_moved_tag_id],
            }
        )

        with pytest.raises(ConflictError, match="still pending"):
            _execute(
                service,
                user_id,
                run_id,
                key="blocked-cost-update",
                revision=4,
                request={"total_spread_pips": 0.5},
                handler=lambda operation, current: {"result": {}},
            )

        operation = repository.find_operation_by_key(user_id, run_id, "reset-key")
        assert operation["state"] == "cleanup_pending"
        response = service.resume_pending_operation(
            user_id,
            run_id,
            operation["_id"],
            cleanup_handler=lambda _op, _run, generation: (
                repository.delete_generation_data(user_id, run_id, generation)
            ),
        )
        run = mongo.db.backtest_runs.find_one({"_id": run_id})
        assert response["state"] == "committed"
        assert run["simulation_control"]["pending_operation_id"] is None
        assert run["simulation_control"]["has_accepted_order"] is False
        assert repository.list_visible_orders(
            user_id, run_id, reset_generation=0, committed_sequence=4
        ) == []
        assert repository.find_visible_cost_profile(
            user_id, run_id, committed_sequence=4
        )["revision"] == 2
        assert mongo.db.trades.find_one({"_id": new_generation_trade_id}) is not None
        assert mongo.db.trades.find_one({"_id": other_run_trade_id}) is not None
        assert mongo.db.tags.find_one({"_id": stop_moved_tag_id}) is not None
        assert mongo.db.tag_categories.find_one({"_id": category_id}) is not None
