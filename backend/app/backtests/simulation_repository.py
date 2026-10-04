"""Run-scoped persistence for Backtest simulation state."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.extensions import mongo
from app.backtests.simulation_schemas import make_default_cost_profile
from app.utils.datetime_utils import utc_now

MAX_PAGE_SIZE = 500


class BacktestSimulationRepository:
    """Persist simulation records separately from the bounded run document.

    Fill allocations use the existing ``executions`` collection, as required
    by the Backtest data model. Orders and positions are immutable versions;
    readers select the newest version whose operation sequence is committed.
    """

    OPERATIONS = "backtest_simulation_operations"
    ORDERS = "backtest_simulation_orders"
    POSITIONS = "backtest_simulation_positions"
    COST_PROFILES = "backtest_simulation_cost_profiles"
    FILLS = "executions"

    def __init__(self, database=None) -> None:
        """Use an explicit database for tests or the app's Mongo database."""
        self._database_override = database

    @property
    def database(self):
        if self._database_override is not None:
            return self._database_override
        return mongo.db

    @staticmethod
    def _as_object_id(value) -> ObjectId | None:
        if isinstance(value, ObjectId):
            return value
        if ObjectId.is_valid(value):
            return ObjectId(value)
        return None

    def _scope(self, user_id, run_id) -> dict[str, ObjectId] | None:
        user_oid = self._as_object_id(user_id)
        run_oid = self._as_object_id(run_id)
        if user_oid is None or run_oid is None:
            return None
        return {"user_id": user_oid, "run_id": run_oid}

    @staticmethod
    def _normalize_document(document: dict[str, Any]) -> dict[str, Any]:
        result = dict(document)
        for field in (
            "user_id",
            "run_id",
            "backtest_run_id",
            "trade_account_id",
            "trade_id",
            "order_id",
            "backtest_order_id",
            "position_id",
            "simulated_position_id",
        ):
            value = result.get(field)
            if value is not None and not isinstance(value, ObjectId):
                if ObjectId.is_valid(value):
                    result[field] = ObjectId(value)
        result.setdefault("_id", ObjectId())
        return result

    def _insert(self, collection_name: str, document: dict[str, Any]):
        normalized = self._normalize_document(document)
        self.database[collection_name].insert_one(normalized)
        return normalized["_id"]

    def insert_operation(self, document: dict[str, Any]) -> ObjectId:
        """Insert an operation journal record; unique indexes fence retries."""
        return self._insert(self.OPERATIONS, document)

    def find_operation_by_key(
        self, user_id, run_id, client_operation_id: str
    ) -> dict | None:
        """Find an idempotency record only within its authenticated scope."""
        scope = self._scope(user_id, run_id)
        if scope is None:
            return None
        return self.database[self.OPERATIONS].find_one(
            {**scope, "client_operation_id": client_operation_id}
        )

    def find_operation_by_sequence(
        self, user_id, run_id, sequence: int
    ) -> dict | None:
        """Find the durable journal record for one run-level sequence."""
        scope = self._scope(user_id, run_id)
        if scope is None:
            return None
        return self.database[self.OPERATIONS].find_one(
            {**scope, "sequence": sequence}
        )

    def find_operation_by_id(self, user_id, run_id, operation_id) -> dict | None:
        """Find a pending operation through its owner and run association."""
        scope = self._scope(user_id, run_id)
        operation_oid = self._as_object_id(operation_id)
        if scope is None or operation_oid is None:
            return None
        return self.database[self.OPERATIONS].find_one(
            {**scope, "_id": operation_oid}
        )

    def update_operation(
        self,
        user_id,
        run_id,
        operation_id,
        updates: dict[str, Any],
        *,
        states: tuple[str, ...] | None = None,
    ) -> bool:
        """Update journal lifecycle fields inside the owner/run scope."""
        scope = self._scope(user_id, run_id)
        operation_oid = self._as_object_id(operation_id)
        allowed = {
            "state",
            "final_state",
            "result",
            "commit_updates",
            "committed_at",
        }
        if (
            scope is None
            or operation_oid is None
            or not updates
            or not set(updates).issubset(allowed)
        ):
            return False
        query = {**scope, "_id": operation_oid}
        if states is not None:
            query["state"] = {"$in": list(states)}
        result = self.database[self.OPERATIONS].update_one(
            query, {"$set": updates}
        )
        return result.matched_count == 1

    def delete_unclaimed_operation(self, user_id, run_id, operation_id) -> bool:
        """Discard an operation journal row that never acquired the run gate."""
        scope = self._scope(user_id, run_id)
        operation_oid = self._as_object_id(operation_id)
        if scope is None or operation_oid is None:
            return False
        result = self.database[self.OPERATIONS].delete_one(
            {**scope, "_id": operation_oid, "state": "pending"}
        )
        return result.deleted_count == 1

    def list_recoverable_operations(self, *, limit: int = 100) -> list[dict]:
        """List durable pending effects for the trusted worker recovery loop."""
        if limit < 1:
            return []
        limit = min(limit, MAX_PAGE_SIZE)
        return list(
            self.database[self.OPERATIONS]
            .find({"state": {"$in": ["pending", "cleanup_pending"]}})
            .sort([("created_at", 1), ("_id", 1)])
            .limit(limit)
        )

    def insert_order_version(self, document: dict[str, Any]) -> ObjectId:
        """Append one version of a stable order id."""
        return self._insert(self.ORDERS, document)

    def insert_fill(self, document: dict[str, Any]) -> ObjectId:
        """Append one fill allocation as an extended Execution document."""
        if "backtest_run_id" not in document:
            raise ValueError("Backtest fill requires backtest_run_id.")
        return self._insert(self.FILLS, document)

    def publish_committed_effects(
        self, user_id, run_id, *, reset_generation: int, operation_sequence: int
    ) -> None:
        """Expose staged fills and closed trades after their run sequence commits.

        Simulation writes use the ordinary executions and trades collections so
        Journal, account, and analytics views can consume them. They remain
        hidden while an operation is pending, then this idempotent publication
        step makes only that operation's records visible.
        """
        scope = self._scope(user_id, run_id)
        if scope is None:
            raise ValueError("Valid user_id and run_id are required.")
        self.database[self.FILLS].update_many(
            {
                "user_id": scope["user_id"],
                "backtest_run_id": scope["run_id"],
                "reset_generation": reset_generation,
                "simulation_operation_sequence": operation_sequence,
                "backtest_order_id": {"$exists": True},
                "simulation_committed": False,
            },
            {"$set": {"simulation_committed": True}},
        )
        self.database.trades.update_many(
            {
                "user_id": scope["user_id"],
                "backtest_run_id": scope["run_id"],
                "simulation_generation": reset_generation,
                "simulation_operation_sequence": operation_sequence,
                "status": "deleted",
            },
            {
                "$set": {"status": "closed", "deleted_at": None},
                "$currentDate": {"updated_at": True},
            },
        )

    def hide_generation_publications(
        self, user_id, run_id, *, reset_generation: int
    ) -> None:
        """Hide one generation's shared Journal records while reset is fenced."""
        scope = self._scope(user_id, run_id)
        if scope is None:
            raise ValueError("Valid user_id and run_id are required.")
        self.database[self.FILLS].update_many(
            {
                "user_id": scope["user_id"],
                "backtest_run_id": scope["run_id"],
                "reset_generation": reset_generation,
                "backtest_order_id": {"$exists": True},
                "simulation_committed": True,
            },
            {"$set": {"simulation_committed": False}},
        )
        self.database.trades.update_many(
            {
                "user_id": scope["user_id"],
                "backtest_run_id": scope["run_id"],
                "simulation_generation": reset_generation,
                "status": "closed",
            },
            {
                "$set": {"status": "deleted"},
                "$currentDate": {"deleted_at": True, "updated_at": True},
            },
        )

    def insert_position_version(self, document: dict[str, Any]) -> ObjectId:
        """Append one version of a stable simulated position."""
        return self._insert(self.POSITIONS, document)

    def insert_cost_profile(self, document: dict[str, Any]) -> ObjectId:
        """Append one immutable cost-profile revision."""
        return self._insert(self.COST_PROFILES, document)

    def ensure_default_cost_profile(
        self, user_id, run_id, *, execution_costs: dict | None = None
    ) -> dict:
        """Create or return revision zero with costs frozen on the run."""
        scope = self._scope(user_id, run_id)
        if scope is None:
            raise ValueError("Valid user_id and run_id are required.")
        collection = self.database[self.COST_PROFILES]
        existing = collection.find_one({**scope, "revision": 0})
        if existing is not None:
            return existing

        document = self._normalize_document(
            make_default_cost_profile(
                **scope, now=utc_now(), execution_costs=execution_costs
            )
        )
        try:
            collection.insert_one(document)
        except DuplicateKeyError:
            # A concurrent initializer won the unique (user, run, revision)
            # insert; return its canonical record.
            existing = collection.find_one({**scope, "revision": 0})
            if existing is None:
                raise
            return existing
        return document

    @staticmethod
    def _latest_version_pipeline(
        query: dict[str, Any],
        *,
        identity_field: str,
        sequence_field: str,
        version_field: str,
        skip: int,
        limit: int,
        extra_match: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = [
            {"$match": query},
            {
                "$sort": {
                    identity_field: 1,
                    sequence_field: -1,
                    version_field: -1,
                    "_id": -1,
                }
            },
            {
                "$group": {
                    "_id": f"${identity_field}",
                    "document": {"$first": "$$ROOT"},
                }
            },
            {"$replaceRoot": {"newRoot": "$document"}},
        ]
        if extra_match:
            pipeline.append({"$match": extra_match})
        pipeline.append({"$sort": {sequence_field: -1, "_id": -1}})
        if skip:
            pipeline.append({"$skip": skip})
        if limit:
            pipeline.append({"$limit": limit})
        return pipeline

    def list_visible_orders(
        self,
        user_id,
        run_id,
        *,
        reset_generation: int,
        committed_sequence: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """Return latest order versions visible at the committed sequence."""
        scope = self._scope(user_id, run_id)
        if scope is None or skip < 0 or limit < 1:
            return []
        limit = min(limit, MAX_PAGE_SIZE)
        query = {
            **scope,
            "reset_generation": reset_generation,
            "operation_sequence": {"$lte": committed_sequence},
        }
        pipeline = self._latest_version_pipeline(
            query,
            identity_field="order_id",
            sequence_field="operation_sequence",
            version_field="entity_version",
            skip=skip,
            limit=limit,
        )
        return list(self.database[self.ORDERS].aggregate(pipeline))

    def list_visible_fills(
        self,
        user_id,
        run_id,
        *,
        reset_generation: int,
        committed_sequence: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """Return append-only fill allocations visible to the committed run."""
        scope = self._scope(user_id, run_id)
        if scope is None or skip < 0 or limit < 1:
            return []
        limit = min(limit, MAX_PAGE_SIZE)
        cursor = self.database[self.FILLS].find(
            {
                "user_id": scope["user_id"],
                "backtest_run_id": scope["run_id"],
                "reset_generation": reset_generation,
                "simulation_operation_sequence": {"$lte": committed_sequence},
                "backtest_order_id": {"$exists": True},
            }
        ).sort(
            [
                ("simulation_operation_sequence", 1),
                ("source_candle_index", 1),
                ("allocation_index", 1),
                ("_id", 1),
            ]
        )
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def list_visible_positions(
        self,
        user_id,
        run_id,
        *,
        reset_generation: int,
        committed_sequence: int,
        open_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """Return latest position versions, excluding uncommitted writes."""
        scope = self._scope(user_id, run_id)
        if scope is None or skip < 0 or limit < 1:
            return []
        limit = min(limit, MAX_PAGE_SIZE)
        query = {
            **scope,
            "reset_generation": reset_generation,
            "operation_sequence": {"$lte": committed_sequence},
        }
        pipeline = self._latest_version_pipeline(
            query,
            identity_field="position_id",
            sequence_field="operation_sequence",
            version_field="entity_version",
            skip=skip,
            limit=limit,
            extra_match={"status": "open"} if open_only else None,
        )
        return list(self.database[self.POSITIONS].aggregate(pipeline))

    def find_visible_cost_profile(
        self,
        user_id,
        run_id,
        *,
        committed_sequence: int,
        execution_costs: dict | None = None,
    ) -> dict | None:
        """Return the newest profile revision visible to the run."""
        scope = self._scope(user_id, run_id)
        if scope is None:
            return None
        profile = self.database[self.COST_PROFILES].find_one(
            {
                **scope,
                "operation_sequence": {"$lte": committed_sequence},
            },
            sort=[("operation_sequence", -1), ("revision", -1)],
        )
        if profile is None:
            return self.ensure_default_cost_profile(
                scope["user_id"], scope["run_id"], execution_costs=execution_costs
            )
        return profile

    def list_operation_history(
        self, user_id, run_id, *, skip: int = 0, limit: int = 100
    ) -> list[dict]:
        """Read a bounded owner-scoped operation journal page."""
        scope = self._scope(user_id, run_id)
        if scope is None or skip < 0 or limit < 1:
            return []
        limit = min(limit, MAX_PAGE_SIZE)
        cursor = self.database[self.OPERATIONS].find(scope).sort(
            [("sequence", -1), ("_id", -1)]
        )
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def delete_generation_data(self, user_id, run_id, reset_generation: int) -> int:
        """Purge reset-generation entities while retaining the operation log
        and cost history, as required by the reset contract.
        """
        scope = self._scope(user_id, run_id)
        if scope is None:
            return 0
        generation_scope = {**scope, "reset_generation": reset_generation}
        deleted = 0
        for name in (self.ORDERS, self.POSITIONS):
            deleted += self.database[name].delete_many(generation_scope).deleted_count
        fill_scope = {
            "user_id": scope["user_id"],
            "backtest_run_id": scope["run_id"],
            "reset_generation": reset_generation,
        }
        deleted += self.database[self.FILLS].delete_many(fill_scope).deleted_count
        trade_scope = {
            "user_id": scope["user_id"],
            "backtest_run_id": scope["run_id"],
            "simulation_generation": reset_generation,
        }
        deleted += self.database.trades.delete_many(trade_scope).deleted_count
        remaining = sum(
            self.database[name].count_documents(generation_scope)
            for name in (self.ORDERS, self.POSITIONS)
        )
        remaining += self.database[self.FILLS].count_documents(fill_scope)
        remaining += self.database.trades.count_documents(trade_scope)
        if remaining:
            raise RuntimeError(
                "Backtest simulation generation cleanup left records behind."
            )
        return deleted

    def delete_run_data(self, user_id, run_id) -> int:
        """Purge all simulation records for a confirmed run deletion."""
        scope = self._scope(user_id, run_id)
        if scope is None:
            return 0
        deleted = 0
        for name in (
            self.OPERATIONS,
            self.ORDERS,
            self.POSITIONS,
            self.COST_PROFILES,
        ):
            deleted += self.database[name].delete_many(scope).deleted_count
        fill_scope = {
            "user_id": scope["user_id"],
            "backtest_run_id": scope["run_id"],
        }
        deleted += self.database[self.FILLS].delete_many(fill_scope).deleted_count
        trade_scope = {
            "user_id": scope["user_id"],
            "backtest_run_id": scope["run_id"],
        }
        deleted += self.database.trades.delete_many(trade_scope).deleted_count
        remaining = sum(
            self.database[name].count_documents(scope)
            for name in (
                self.OPERATIONS,
                self.ORDERS,
                self.POSITIONS,
                self.COST_PROFILES,
            )
        )
        remaining += self.database[self.FILLS].count_documents(fill_scope)
        remaining += self.database.trades.count_documents(trade_scope)
        if remaining:
            raise RuntimeError("Backtest run cleanup left simulation records behind.")
        return deleted
