"""Owner-scoped MongoDB persistence for Backtest runs and notices."""

from __future__ import annotations

from datetime import timedelta

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.extensions import mongo
from app.repositories.base import BaseRepository
from app.utils.datetime_utils import utc_now


def _object_id(value) -> ObjectId | None:
    """Parse an ObjectId value without exposing malformed-id errors."""
    if isinstance(value, ObjectId):
        return value
    if not ObjectId.is_valid(value):
        return None
    return ObjectId(value)


class BacktestRepository(BaseRepository):
    """Owner-scoped operations over backtest_runs and related records."""

    collection_name = "backtest_runs"

    def create_run(self, document: dict) -> ObjectId:
        """Insert a run and return its BSON identifier."""
        run_id = document.get("_id") or ObjectId()
        document["_id"] = run_id
        self.collection.insert_one(document)
        return run_id

    def find_owned_run(self, user_id: str, run_id) -> dict | None:
        """Find a run only when its authenticated owner matches."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return None
        return self.find_one(
            {"_id": run_oid, "user_id": ObjectId(user_id)}
        )

    def list_by_user(self, user_id: str) -> list[dict]:
        """Return retained runs for a user, newest first."""
        return self.find_many(
            {
                "user_id": ObjectId(user_id),
                "status": {
                    "$in": ["selecting_period", "preparing", "ready", "deleting"]
                },
            },
            sort=[("created_at", -1), ("_id", -1)],
        )

    def update_owned_run(
        self, user_id: str, run_id, updates: dict
    ) -> bool:
        """Apply one update only to a run owned by the caller."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return False
        updates["updated_at"] = utc_now()
        result = self.collection.update_one(
            {"_id": run_oid, "user_id": ObjectId(user_id)},
            {"$set": updates},
        )
        return result.matched_count == 1

    def set_missing_blind_reference(
        self, user_id: str, run_id, reference_price: float
    ) -> bool:
        """Backfill a legacy blind run without replacing an established value."""
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        if run_oid is None or user_oid is None:
            return False
        result = self.collection.update_one(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "status": "ready",
                "blind_mode": True,
                "$or": [
                    {"normalized_reference_price": None},
                    {"normalized_reference_price": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "normalized_reference_price": reference_price,
                    "updated_at": utc_now(),
                }
            },
        )
        return result.modified_count == 1

    def request_deletion(self, user_id: str, run_id, *, now) -> dict | None:
        """Atomically turn an owned deletable run into a cleanup marker."""
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        if run_oid is None or user_oid is None:
            return None
        return self.collection.find_one_and_update(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "status": {
                    "$in": [
                        "selecting_period",
                        "preparing",
                        "ready",
                        "complete",
                    ]
                },
            },
            {
                "$set": {
                    "status": "deleting",
                    "progress": {"stage": "deleting", "percent": None},
                    "deletion_requested_at": now,
                    "deletion_requested_by": user_oid,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    def find_deletion_candidate(self, *, now) -> dict | None:
        """Find a deletion whose prior preparation lease has expired."""
        return self.collection.find_one(
            {
                "status": "deleting",
                "$and": [
                    {
                        "$or": [
                            {"preparation_lease_expires_at": {"$lte": now}},
                            {"preparation_lease_expires_at": None},
                            {"preparation_lease_expires_at": {"$exists": False}},
                        ]
                    },
                    {
                        "$or": [
                            {"deletion_lease_expires_at": {"$lte": now}},
                            {"deletion_lease_expires_at": None},
                            {"deletion_lease_expires_at": {"$exists": False}},
                        ]
                    },
                ],
            },
            sort=[("deletion_requested_at", 1), ("_id", 1)],
        )

    def claim_deletion_lease(
        self, user_id, run_id, worker_id: str, *, now, lease_seconds: int
    ) -> dict | None:
        """Claim cleanup only after preparation has released its run lease."""
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        if run_oid is None or user_oid is None:
            return None
        return self.collection.find_one_and_update(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "status": "deleting",
                "$and": [
                    {
                        "$or": [
                            {"preparation_lease_expires_at": {"$lte": now}},
                            {"preparation_lease_expires_at": None},
                            {"preparation_lease_expires_at": {"$exists": False}},
                        ]
                    },
                    {
                        "$or": [
                            {"deletion_lease_expires_at": {"$lte": now}},
                            {"deletion_lease_expires_at": None},
                            {"deletion_lease_expires_at": {"$exists": False}},
                        ]
                    },
                ],
            },
            {
                "$set": {
                    "deletion_lease_owner": worker_id,
                    "deletion_lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                },
                "$inc": {"deletion_attempt_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )

    def renew_deletion_lease(
        self, user_id, run_id, worker_id: str, *, now, lease_seconds: int
    ) -> bool:
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        if run_oid is None or user_oid is None:
            return False
        result = self.collection.update_one(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "status": "deleting",
                "deletion_lease_owner": worker_id,
                "deletion_lease_expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "deletion_lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1

    def release_deletion_lease(self, user_id, run_id, worker_id: str) -> None:
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        if run_oid is None or user_oid is None:
            return
        self.collection.update_one(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "status": "deleting",
                "deletion_lease_owner": worker_id,
            },
            {
                "$unset": {
                    "deletion_lease_owner": "",
                    "deletion_lease_expires_at": "",
                }
            },
        )

    def finish_deletion(self, user_id, run_id, worker_id: str, *, now) -> bool:
        """Remove all MongoDB associations and the run marker last."""
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        if run_oid is None or user_oid is None:
            return False
        lease_query = {
            "_id": run_oid,
            "user_id": user_oid,
            "status": "deleting",
            "deletion_lease_owner": worker_id,
            "deletion_lease_expires_at": {"$gt": now},
        }
        run = self.collection.find_one(lease_query)
        if run is None:
            return False

        for collection_name in (
            "backtest_chart_tabs",
            "backtest_chart_workspaces",
            "backtest_drawing_states",
            "backtest_preparation_jobs",
            "backtest_notices",
        ):
            mongo.db[collection_name].delete_many(
                {"user_id": user_oid, "run_id": run_oid}
            )
        mongo.db.trade_accounts.delete_many(
            {
                "user_id": user_oid,
                "workspace_mode": "backtest",
                "$or": [
                    {"backtest_run_id": run_oid},
                    {"_id": run.get("account_id")},
                ],
            }
        )
        result = self.collection.delete_one(lease_query)
        return result.deleted_count == 1

    def update_progress(
        self,
        user_id: str,
        run_id,
        *,
        stage: str,
        percent: float | None,
    ) -> bool:
        """Persist the public preparation progress on its run."""
        return self.update_owned_run(
            user_id,
            run_id,
            {"progress": {"stage": stage, "percent": percent}},
        )

    def update_leased_progress(
        self,
        user_id: str,
        run_id,
        worker_id: str,
        *,
        stage: str,
        percent: float | None,
        now,
    ) -> bool:
        run_oid = _object_id(run_id)
        if run_oid is None:
            return False
        result = self.collection.update_one(
            {
                "_id": run_oid,
                "user_id": ObjectId(user_id),
                "status": {"$in": ["selecting_period", "preparing"]},
                "preparation_lease_owner": worker_id,
                "preparation_lease_expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "progress": {"stage": stage, "percent": percent},
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1

    def cleanup_orphan_associations(self, user_id, run_id) -> None:
        """Finish account/tab cleanup after a terminal run delete was committed."""
        user_oid = _object_id(user_id)
        run_oid = _object_id(run_id)
        if user_oid is None or run_oid is None:
            return
        mongo.db.trade_accounts.delete_one(
            {"user_id": user_oid, "backtest_run_id": run_oid}
        )
        mongo.db.backtest_chart_tabs.delete_many(
            {"user_id": user_oid, "run_id": run_oid}
        )
        mongo.db.backtest_chart_workspaces.delete_many(
            {"user_id": user_oid, "run_id": run_oid}
        )
        mongo.db.backtest_drawing_states.delete_many(
            {"user_id": user_oid, "run_id": run_oid}
        )

    def mark_ready(
        self,
        user_id: str,
        run_id,
        *,
        snapshot: dict,
        coverage: dict,
        warmup_coverage: dict,
        replay_start_source_index: int,
        first_time_ms: int,
        normalized_reference_price: float | None = None,
        worker_id: str,
        now,
    ) -> bool:
        """Atomically publish snapshot, coverage, ready status, and cursor."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return False
        result = self.collection.update_one(
            {
                "_id": run_oid,
                "user_id": ObjectId(user_id),
                "status": "preparing",
                "snapshot": None,
                "preparation_lease_owner": worker_id,
                "preparation_lease_expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "snapshot": snapshot,
                    "coverage": coverage,
                    "warmup_coverage": warmup_coverage,
                    "normalized_reference_price": normalized_reference_price,
                    "status": "ready",
                    "progress": {"stage": "complete", "percent": 100},
                    "replay_cursor": {
                        "source_candle_index": replay_start_source_index,
                        "time_ms": first_time_ms,
                        "furthest_source_candle_index": replay_start_source_index,
                        "furthest_time_ms": first_time_ms,
                        "revision": 0,
                        "updated_at": now,
                    },
                    "updated_at": now,
                },
                "$unset": {
                    "preparation_lease_owner": "",
                    "preparation_lease_expires_at": "",
                },
            },
        )
        return result.modified_count == 1

    def resolve_random_selection(
        self,
        user_id: str,
        run_id,
        worker_id: str,
        *,
        account_id: ObjectId,
        start_date,
        end_date,
        start_utc_ms: int,
        end_utc_ms: int,
        context_start_utc_ms: int,
        now,
    ) -> dict | None:
        """Persist the chosen period and transition selection into preparation."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return None
        user_oid = ObjectId(user_id)
        start_text = start_date.isoformat()
        end_text = end_date.isoformat()
        resolved = self.collection.find_one_and_update(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "status": "selecting_period",
                "preparation_lease_owner": worker_id,
                "preparation_lease_expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "requested_start_date": start_text,
                    "requested_end_date": end_text,
                    "start_utc_ms": start_utc_ms,
                    "end_utc_ms": end_utc_ms,
                    "context_start_utc_ms": context_start_utc_ms,
                    "account_id": account_id,
                    "status": "preparing",
                    "progress": {"stage": "downloading", "percent": None},
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if resolved is not None:
            return resolved
        # Recovery may see a run already transitioned before its job checkpoint.
        return self.collection.find_one(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "status": "preparing",
                "requested_start_date": start_text,
                "requested_end_date": end_text,
                "account_id": account_id,
                "preparation_lease_owner": worker_id,
                "preparation_lease_expires_at": {"$gt": now},
            }
        )

    def claim_preparation_lease(
        self,
        user_id,
        run_id,
        worker_id: str,
        *,
        now,
        lease_seconds: int,
    ) -> dict | None:
        """Atomically acquire the publication/cleanup fence on a run."""
        from pymongo import ReturnDocument

        run_oid = _object_id(run_id)
        if run_oid is None:
            return None
        expiry = now + timedelta(seconds=lease_seconds)
        return self.collection.find_one_and_update(
            {
                "_id": run_oid,
                "user_id": ObjectId(user_id),
                "status": {"$in": ["selecting_period", "preparing"]},
                "$or": [
                    {"preparation_lease_expires_at": {"$lte": now}},
                    {"preparation_lease_expires_at": None},
                    {"preparation_lease_expires_at": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "preparation_lease_owner": worker_id,
                    "preparation_lease_expires_at": expiry,
                    "updated_at": now,
                },
                "$inc": {"preparation_lease_generation": 1},
            },
            return_document=ReturnDocument.AFTER,
        )

    def renew_preparation_lease(
        self, user_id, run_id, worker_id: str, *, now, lease_seconds: int
    ) -> bool:
        run_oid = _object_id(run_id)
        if run_oid is None:
            return False
        result = self.collection.update_one(
            {
                "_id": run_oid,
                "user_id": ObjectId(user_id),
                "status": {"$in": ["selecting_period", "preparing"]},
                "preparation_lease_owner": worker_id,
                "preparation_lease_expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "preparation_lease_expires_at": now
                    + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1

    def release_preparation_lease(self, run_id, worker_id: str) -> None:
        run_oid = _object_id(run_id)
        if run_oid is None:
            return
        self.collection.update_one(
            {"_id": run_oid, "preparation_lease_owner": worker_id},
            {
                "$unset": {
                    "preparation_lease_owner": "",
                    "preparation_lease_expires_at": "",
                }
            },
        )

    def delete_leased_run(
        self, user_id: str, run_id, worker_id: str, *, now
    ) -> bool:
        """Delete run/account only while this worker holds the live run fence."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return False
        user_oid = ObjectId(user_id)
        result = self.collection.delete_one(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "status": {"$in": ["selecting_period", "preparing"]},
                "preparation_lease_owner": worker_id,
                "preparation_lease_expires_at": {"$gt": now},
            }
        )
        if result.deleted_count != 1:
            return False
        mongo.db.trade_accounts.delete_one(
            {"user_id": user_oid, "backtest_run_id": run_oid}
        )
        mongo.db.backtest_chart_tabs.delete_many(
            {"user_id": user_oid, "run_id": run_oid}
        )
        mongo.db.backtest_chart_workspaces.delete_many(
            {"user_id": user_oid, "run_id": run_oid}
        )
        mongo.db.backtest_drawing_states.delete_many(
            {"user_id": user_oid, "run_id": run_oid}
        )
        return True

    def delete_owned_run(self, user_id: str, run_id) -> bool:
        """Delete an owned run and its associated Backtest account."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return False
        user_oid = ObjectId(user_id)
        result = self.collection.delete_one(
            {"_id": run_oid, "user_id": user_oid}
        )
        if result.deleted_count:
            mongo.db.trade_accounts.delete_one(
                {"user_id": user_oid, "backtest_run_id": run_oid}
            )
            mongo.db.backtest_chart_tabs.delete_many(
                {"user_id": user_oid, "run_id": run_oid}
            )
            mongo.db.backtest_chart_workspaces.delete_many(
                {"user_id": user_oid, "run_id": run_oid}
            )
            mongo.db.backtest_drawing_states.delete_many(
                {"user_id": user_oid, "run_id": run_oid}
            )
            return True
        return False

    def list_chart_tabs(self, user_id: str, run_id) -> list[dict]:
        """Return the owned run's tabs in display order."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return []
        return list(
            mongo.db.backtest_chart_tabs.find(
                {"user_id": ObjectId(user_id), "run_id": run_oid}
            ).sort([("position", 1), ("id", 1)])
        )

    def delete_chart_tabs(self, user_id: str, run_id) -> None:
        """Remove legacy flat tabs after their layout has been persisted."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return
        mongo.db.backtest_chart_tabs.delete_many(
            {"user_id": ObjectId(user_id), "run_id": run_oid}
        )

    def find_chart_workspace(self, user_id: str, run_id) -> dict | None:
        """Find the one persisted dock layout owned by the caller and run."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return None
        return mongo.db.backtest_chart_workspaces.find_one(
            {"user_id": ObjectId(user_id), "run_id": run_oid}
        )

    def compare_and_set_chart_workspace(
        self,
        user_id: str,
        run_id,
        *,
        expected_revision: int,
        workspace: dict,
        now,
    ) -> dict | None:
        """Atomically insert/update a workspace at its expected revision."""
        from pymongo import ReturnDocument

        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        if run_oid is None or user_oid is None:
            return None
        query = {
            "user_id": user_oid,
            "run_id": run_oid,
            "revision": expected_revision,
        }
        update = {
            "$set": {
                **workspace,
                "revision": expected_revision + 1,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        }
        try:
            return mongo.db.backtest_chart_workspaces.find_one_and_update(
                query,
                update,
                upsert=expected_revision == 0,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # A competing revision-zero initializer can win the unique key.
            return None

    def compare_and_set_replay_cursor(
        self,
        user_id: str,
        run_id,
        *,
        expected_revision: int,
        source_candle_index: int,
        time_ms: int,
        furthest_source_candle_index: int,
        furthest_time_ms: int,
        now,
    ) -> dict | None:
        """Advance the owner's replay cursor if its revision still matches."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return None
        revision = expected_revision + 1
        cursor = {
            "source_candle_index": source_candle_index,
            "time_ms": time_ms,
            "furthest_source_candle_index": furthest_source_candle_index,
            "furthest_time_ms": furthest_time_ms,
            "revision": revision,
            "updated_at": now,
        }
        result = self.collection.update_one(
            {
                "_id": run_oid,
                "user_id": ObjectId(user_id),
                "status": "ready",
                "replay_cursor.revision": expected_revision,
            },
            {
                "$set": {
                    "replay_cursor": cursor,
                    "updated_at": now,
                }
            },
        )
        return cursor if result.matched_count == 1 else None

    def ensure_simulation_control(self, user_id: str, run_id) -> dict | None:
        """Initialize/complete the bounded CAS fields on an owned ready run."""
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        if run_oid is None or user_oid is None:
            return None
        query = {
            "_id": run_oid,
            "user_id": user_oid,
            "status": {"$in": ["ready", "complete"]},
        }
        defaults = {
            "committed_sequence": 0,
            "control_revision": 0,
            "reset_generation": 0,
            "has_accepted_order": False,
            "pending_operation_id": None,
        }
        run = self.collection.find_one(query)
        if run is None:
            return None
        control = run.get("simulation_control")
        if not isinstance(control, dict):
            self.collection.update_one(
                {
                    **query,
                    "$or": [
                        {"simulation_control": {"$exists": False}},
                        {"simulation_control": None},
                    ],
                },
                {
                    "$set": {
                        "simulation_control": defaults,
                        "updated_at": utc_now(),
                    }
                },
            )
        else:
            for field_name, value in defaults.items():
                if field_name in control:
                    continue
                self.collection.update_one(
                    {
                        **query,
                        f"simulation_control.{field_name}": {"$exists": False},
                    },
                    {
                        "$set": {
                            f"simulation_control.{field_name}": value,
                            "updated_at": utc_now(),
                        }
                    },
                )
        return self.collection.find_one(query)

    def reserve_simulation_operation(
        self,
        user_id: str,
        run_id,
        *,
        operation_id,
        kind: str,
        sequence: int,
        reset_generation: int,
        expected_revision: int,
        now=None,
    ) -> dict | None:
        """Claim the run gate with one owner-scoped compare-and-swap."""
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        operation_oid = _object_id(operation_id)
        if run_oid is None or user_oid is None or operation_oid is None:
            return None
        allowed_statuses = (
            ["ready", "complete"]
            if kind in {"reset", "rewind"}
            else ["ready"]
        )
        query = {
            "_id": run_oid,
            "user_id": user_oid,
            "status": {"$in": allowed_statuses},
            "simulation_control.committed_sequence": sequence - 1,
            "simulation_control.control_revision": expected_revision,
            "simulation_control.reset_generation": reset_generation,
            "$or": [
                {"simulation_control.pending_operation_id": None},
                {"simulation_control.pending_operation_id": {"$exists": False}},
            ],
        }
        now = now or utc_now()
        result = self.collection.update_one(
            query,
            {
                "$set": {
                    "simulation_control.pending_operation_id": operation_oid,
                    "updated_at": now,
                },
                "$inc": {"simulation_control.control_revision": 1},
            },
        )
        if result.matched_count != 1:
            return None
        return self.collection.find_one({"_id": run_oid, "user_id": user_oid})

    def commit_simulation_operation(
        self,
        user_id: str,
        run_id,
        *,
        operation_id,
        sequence: int,
        reset_generation: int,
        control_revision: int,
        run_updates: dict | None = None,
        accepted_order: bool = False,
        allow_complete: bool = False,
        now=None,
    ) -> bool:
        """Publish staged effects and clear the gate in the same run CAS."""
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        operation_oid = _object_id(operation_id)
        if run_oid is None or user_oid is None or operation_oid is None:
            return False
        updates = dict(run_updates or {})
        if "simulation_control" in updates or any(
            key.startswith("simulation_control.") for key in updates
        ):
            raise ValueError("run_updates cannot mutate simulation_control.")
        if updates.get("status", "ready") not in {"ready", "complete"}:
            raise ValueError(
                "Simulation commits may only leave a run ready or complete."
            )
        now = now or utc_now()
        query = {
            "_id": run_oid,
            "user_id": user_oid,
            "status": {"$in": ["ready", "complete"]}
            if allow_complete
            else "ready",
            "simulation_control.pending_operation_id": operation_oid,
            "simulation_control.committed_sequence": sequence - 1,
            "simulation_control.reset_generation": reset_generation,
            "simulation_control.control_revision": control_revision,
        }
        set_values = {
            **updates,
            "simulation_control.committed_sequence": sequence,
            "simulation_control.pending_operation_id": None,
            "updated_at": now,
        }
        if accepted_order:
            set_values["simulation_control.has_accepted_order"] = True
        result = self.collection.update_one(query, {"$set": set_values})
        return result.matched_count == 1

    def begin_simulation_reset(
        self,
        user_id: str,
        run_id,
        *,
        operation_id,
        sequence: int,
        previous_generation: int,
        control_revision: int,
        run_updates: dict | None = None,
        now=None,
    ) -> bool:
        """Commit a new reset generation while retaining the cleanup gate."""
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        operation_oid = _object_id(operation_id)
        if run_oid is None or user_oid is None or operation_oid is None:
            return False
        updates = dict(run_updates or {})
        if "simulation_control" in updates or any(
            key.startswith("simulation_control.") for key in updates
        ):
            raise ValueError("run_updates cannot mutate simulation_control.")
        updates["status"] = "ready"
        now = now or utc_now()
        query = {
            "_id": run_oid,
            "user_id": user_oid,
            "status": {"$in": ["ready", "complete"]},
            "simulation_control.pending_operation_id": operation_oid,
            "simulation_control.committed_sequence": sequence - 1,
            "simulation_control.reset_generation": previous_generation,
            "simulation_control.control_revision": control_revision,
        }
        set_values = {
            **updates,
            "simulation_control.committed_sequence": sequence,
            "simulation_control.reset_generation": previous_generation + 1,
            "simulation_control.has_accepted_order": False,
            # Keep this operation as the gate until its old generation is purged.
            "simulation_control.pending_operation_id": operation_oid,
            "updated_at": now,
        }
        result = self.collection.update_one(query, {"$set": set_values})
        if result.matched_count == 1:
            return True
        # A retry after a crash between the CAS and operation-journal update
        # recognizes the already-applied generation transition.
        run = self.collection.find_one(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "simulation_control.pending_operation_id": operation_oid,
                "simulation_control.committed_sequence": sequence,
                "simulation_control.reset_generation": previous_generation + 1,
            }
        )
        return run is not None

    def finish_simulation_reset(
        self,
        user_id: str,
        run_id,
        *,
        operation_id,
        sequence: int,
        reset_generation: int,
        now=None,
    ) -> bool:
        """Release the mutation gate only after reset cleanup has completed."""
        run_oid = _object_id(run_id)
        user_oid = _object_id(user_id)
        operation_oid = _object_id(operation_id)
        if run_oid is None or user_oid is None or operation_oid is None:
            return False
        result = self.collection.update_one(
            {
                "_id": run_oid,
                "user_id": user_oid,
                "status": "ready",
                "simulation_control.pending_operation_id": operation_oid,
                "simulation_control.committed_sequence": sequence,
                "simulation_control.reset_generation": reset_generation,
            },
            {
                "$set": {
                    "simulation_control.pending_operation_id": None,
                    "updated_at": now or utc_now(),
                }
            },
        )
        return result.matched_count == 1

    def list_pending_simulation_runs(
        self, *, user_id: str | None = None, run_id=None, limit: int = 100
    ) -> list[dict]:
        """Find runs with a durable operation gate for worker recovery."""
        if limit < 1:
            return []
        query = {
            "status": {"$in": ["ready", "complete"]},
            "simulation_control.pending_operation_id": {
                "$exists": True,
                "$ne": None,
            },
        }
        if user_id is not None:
            user_oid = _object_id(user_id)
            if user_oid is None:
                return []
            query["user_id"] = user_oid
        if run_id is not None:
            run_oid = _object_id(run_id)
            if run_oid is None:
                return []
            query["_id"] = run_oid
        return list(
            self.collection.find(query)
            .sort([("updated_at", 1), ("_id", 1)])
            .limit(min(limit, 100))
        )

    def find_drawing_state(
        self, user_id: str, run_id, interval_minutes: int
    ) -> dict | None:
        """Find the drawing set for one owner, run, and chart interval."""
        run_oid = _object_id(run_id)
        if run_oid is None:
            return None
        return mongo.db.backtest_drawing_states.find_one(
            {
                "user_id": ObjectId(user_id),
                "run_id": run_oid,
                "interval_minutes": interval_minutes,
            }
        )

    def compare_and_set_drawing_state(
        self,
        user_id: str,
        run_id,
        *,
        interval_minutes: int,
        candlekit_version: str,
        schema_version: int,
        serialized_state: str,
        expected_revision: int,
        now,
    ) -> dict | None:
        """Create/update one interval's payload only at its expected revision."""
        from pymongo import ReturnDocument

        run_oid = _object_id(run_id)
        if run_oid is None:
            return None
        query = {
            "user_id": ObjectId(user_id),
            "run_id": run_oid,
            "interval_minutes": interval_minutes,
            "revision": expected_revision,
        }
        update = {
            "$set": {
                "candlekit_version": candlekit_version,
                "schema_version": schema_version,
                "serialized_state": serialized_state,
                "revision": expected_revision + 1,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        }
        try:
            return mongo.db.backtest_drawing_states.find_one_and_update(
                query,
                update,
                upsert=expected_revision == 0,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # With expected revision zero, a competing first save may insert
            # the unique owner/run/interval row first. The caller maps this
            # same CAS miss to a 409 conflict.
            return None

    def add_notice(self, document: dict) -> ObjectId:
        """Persist a user-scoped failure/no-data notice."""
        notice_id = document.get("_id") or ObjectId()
        document["_id"] = notice_id
        try:
            mongo.db.backtest_notices.insert_one(document)
        except Exception:
            if not mongo.db.backtest_notices.find_one({"_id": notice_id}):
                raise
        return notice_id

    def list_notices(self, user_id: str) -> list[dict]:
        """Return the caller's undismissed notices, newest first."""
        return list(
            mongo.db.backtest_notices.find(
                {"user_id": ObjectId(user_id), "dismissed": False}
            ).sort([("created_at", -1), ("_id", -1)])
        )

    def dismiss_notice(self, user_id: str, notice_id) -> bool:
        """Dismiss one notice only when it belongs to the caller."""
        notice_oid = _object_id(notice_id)
        if notice_oid is None:
            return False
        result = mongo.db.backtest_notices.update_one(
            {"_id": notice_oid, "user_id": ObjectId(user_id)},
            {"$set": {"dismissed": True, "updated_at": utc_now()}},
        )
        return result.matched_count == 1


class PreparationJobRepository:
    """Durable MongoDB lease and checkpoint operations for preparation."""

    @property
    def collection(self):
        return mongo.db.backtest_preparation_jobs

    def create(self, document: dict) -> ObjectId:
        job_id = document.get("_id") or ObjectId()
        document["_id"] = job_id
        self.collection.insert_one(document)
        return job_id

    def find_candidate(self, *, now) -> dict | None:
        """Peek the oldest queued or expired job for run-lease fencing."""
        return self.collection.find_one(
            {
                "$or": [
                    {"state": "queued"},
                    {
                        "state": "running",
                        "$or": [
                            {"lease_expires_at": {"$lte": now}},
                            {"lease_expires_at": None},
                            {"lease_expires_at": {"$exists": False}},
                        ],
                    },
                ]
            },
            sort=[("created_at", 1), ("_id", 1)],
        )

    def claim(
        self,
        job_id,
        worker_id: str,
        *,
        now,
        lease_seconds: int,
    ) -> dict | None:
        """Atomically claim one queued or expired preparation job."""
        from datetime import timedelta

        from pymongo import ReturnDocument

        expiry = now + timedelta(seconds=lease_seconds)
        return self.collection.find_one_and_update(
            {
                "_id": job_id,
                "$and": [
                    {"terminal_outcome": {"$exists": False}},
                    {
                        "$or": [
                            {"state": "queued"},
                            {
                                "state": "running",
                                "$or": [
                                    {"lease_expires_at": {"$lte": now}},
                                    {"lease_expires_at": None},
                                    {"lease_expires_at": {"$exists": False}},
                                ],
                            },
                        ]
                    },
                ],
            },
            {
                "$set": {
                    "state": "running",
                    "lease_owner": worker_id,
                    "lease_expires_at": expiry,
                    "updated_at": now,
                },
                "$inc": {"attempt_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )

    def claim_terminal_cleanup(
        self,
        job_id,
        worker_id: str,
        *,
        now,
        lease_seconds: int,
    ) -> dict | None:
        """Reclaim a recorded terminal result after its prior lease expires."""
        from datetime import timedelta

        from pymongo import ReturnDocument

        return self.collection.find_one_and_update(
            {
                "_id": job_id,
                "state": "running",
                "terminal_outcome": {"$exists": True},
                "$or": [
                    {"lease_expires_at": {"$lte": now}},
                    {"lease_expires_at": None},
                    {"lease_expires_at": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "lease_owner": worker_id,
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                },
                "$inc": {"attempt_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )

    def renew_lease(
        self,
        job_id,
        worker_id: str,
        *,
        now,
        lease_seconds: int,
    ) -> bool:
        from datetime import timedelta

        result = self.collection.update_one(
            {
                "_id": job_id,
                "state": "running",
                "lease_owner": worker_id,
                "lease_expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1

    def add_checkpoint(
        self,
        job_id,
        worker_id: str,
        *,
        now,
        utc_date,
        outcome: str,
        object_key: str | None,
        next_utc_date,
    ) -> bool:
        """Commit a date result once, only for its live lease holder."""
        result = self.collection.update_one(
            {
                "_id": job_id,
                "state": "running",
                "lease_owner": worker_id,
                "lease_expires_at": {"$gt": now},
                "terminal_outcome": {"$exists": False},
                "completed_utc_dates.utc_date": {"$ne": utc_date},
            },
            {
                "$push": {
                    "completed_utc_dates": {
                        "utc_date": utc_date,
                        "outcome": outcome,
                        "object_key": object_key,
                        "completed_at": now,
                    }
                },
                "$set": {
                    "next_utc_date": next_utc_date,
                    "updated_at": now,
                },
            },
        )
        if result.modified_count == 1:
            return True
        # A repeated checkpoint is safe if another pass already committed the
        # same date. The lease owner is still checked to fence stale workers.
        job = self.collection.find_one(
            {
                "_id": job_id,
                "state": "running",
                "lease_owner": worker_id,
                "lease_expires_at": {"$gt": now},
                "terminal_outcome": {"$exists": False},
            }
        )
        return bool(
            job
            and any(
                item.get("utc_date") == utc_date
                for item in job.get("completed_utc_dates", [])
            )
        )

    def save_selection_state(
        self, job_id, worker_id: str, *, selection: dict, now
    ) -> bool:
        """Checkpoint candidate attempts under the live preparation lease."""
        result = self.collection.update_one(
            {
                "_id": job_id,
                "state": "running",
                "lease_owner": worker_id,
                "lease_expires_at": {"$gt": now},
                "terminal_outcome": {"$exists": False},
            },
            {"$set": {"selection": selection, "updated_at": now}},
        )
        return result.matched_count == 1

    def commit_selected_period(
        self,
        job_id,
        worker_id: str,
        *,
        start_date,
        end_date,
        context_start_utc_date,
        end_utc_date,
        now,
    ) -> dict | None:
        """Convert a selected search job into its normal dated preparation job."""
        from datetime import datetime, time, timezone

        return self.collection.find_one_and_update(
            {
                "_id": job_id,
                "state": "running",
                "lease_owner": worker_id,
                "lease_expires_at": {"$gt": now},
                "terminal_outcome": {"$exists": False},
                "selection.status": "selected",
            },
            {
                "$set": {
                    "requested_start_date": start_date.isoformat(),
                    "requested_end_date": end_date.isoformat(),
                    "context_start_utc_date": datetime.combine(
                        context_start_utc_date, time.min, tzinfo=timezone.utc
                    ),
                    "next_utc_date": datetime.combine(
                        context_start_utc_date, time.min, tzinfo=timezone.utc
                    ),
                    "end_utc_date": datetime.combine(
                        end_utc_date, time.min, tzinfo=timezone.utc
                    ),
                    "selection.status": "committed",
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    def mark_completed(self, job_id, worker_id: str, *, now) -> bool:
        result = self.collection.update_one(
            {
                "_id": job_id,
                "state": "running",
                "lease_owner": worker_id,
                "lease_expires_at": {"$gt": now},
                "terminal_outcome": {"$exists": False},
            },
            {
                "$set": {
                    "state": "completed",
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count == 1

    def mark_recovered_completed(self, run_id, *, now) -> bool:
        """Finish a job whose run was atomically published before shutdown."""
        result = self.collection.update_one(
            {"run_id": run_id, "state": {"$ne": "completed"}},
            {
                "$set": {
                    "state": "completed",
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1

    def mark_terminal(
        self,
        job_id,
        worker_id: str,
        *,
        now,
        outcome: str,
        error_type: str | None = None,
        terminal_message: str | None = None,
    ) -> dict | None:
        """Persist a terminal outcome only under the current live job lease."""
        from pymongo import ReturnDocument

        return self.collection.find_one_and_update(
            {
                "_id": job_id,
                "state": "running",
                "lease_owner": worker_id,
                "lease_expires_at": {"$gt": now},
                "terminal_outcome": {"$exists": False},
            },
            {
                "$set": {
                    "terminal_outcome": outcome,
                    "terminal_error_type": error_type,
                    "terminal_message": terminal_message,
                    "terminal_notice_id": ObjectId(),
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    def requeue(self, run_id, *, now) -> bool:
        """Idempotently keep queued work queued, or reclaim expired work."""
        result = self.collection.update_one(
            {
                "run_id": run_id,
                "terminal_outcome": {"$exists": False},
                "$or": [
                    {"state": "queued"},
                    {
                        "state": "running",
                        "$or": [
                            {"lease_expires_at": {"$lte": now}},
                            {"lease_expires_at": None},
                            {"lease_expires_at": {"$exists": False}},
                        ],
                    },
                ],
            },
            {
                "$set": {
                    "state": "queued",
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1

    def delete_for_run(self, run_id) -> dict | None:
        return self.collection.find_one_and_delete({"run_id": run_id})

    def cancel_for_run(self, run_id, *, now) -> bool:
        """Fence queued/running preparation work without releasing its run lease."""
        result = self.collection.update_one(
            {"run_id": run_id, "state": {"$in": ["queued", "running"]}},
            {
                "$set": {
                    "state": "cancelled",
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1
