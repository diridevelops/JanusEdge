"""Portable backup export and restore helpers."""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List
import json
import zipfile

from bson import ObjectId, json_util

from app.auth.schemas import BackupManifestSchema
from app.backtests.candle_cache import BacktestCandleCache
from app.extensions import mongo
from app.market_data.symbol_mapper import (
    get_effective_market_data_mappings,
    get_effective_symbol_mappings,
    resolve_market_data_storage_symbol,
    validate_market_data_mappings,
    validate_symbol_mappings,
)
from app.media.service import MediaService
from app.models.user import (
    DEFAULT_RISK_BREAKEVEN_R_THRESHOLD,
    DEFAULT_STARTING_EQUITY,
)
from app.repositories.account_repo import AccountRepository
from app.repositories.execution_repo import ExecutionRepository
from app.repositories.import_batch_repo import (
    ImportBatchRepository,
)
from app.repositories.market_data_repo import (
    MarketDataRepository,
)
from app.repositories.media_repo import MediaRepository
from app.repositories.tag_repo import TagRepository
from app.repositories.trade_repo import TradeRepository
from app.repositories.user_repo import UserRepository
from app.storage import (
    ensure_bucket_exists,
    get_bucket,
    get_client,
    get_market_data_bucket,
)
from app.utils.errors import ValidationError
from app.utils.trade_fingerprint import (
    build_trade_fingerprint,
)
from app.utils.validators import is_valid_timezone


BACKUP_ARCHIVE_TYPE = "janusedge-portable-backup"
BACKUP_ARCHIVE_VERSION = "1.1"
MANIFEST_PATH = "manifest.json"
DATA_PATH = "data.json"
MEDIA_PREFIX = "media"
MARKET_DATA_PREFIX = "market-data"


class PortableBackupService:
    """Create and restore portable user backups."""

    def __init__(self) -> None:
        self.user_repo = UserRepository()
        self.account_repo = AccountRepository()
        self.tag_repo = TagRepository()
        self.batch_repo = ImportBatchRepository()
        self.trade_repo = TradeRepository()
        self.execution_repo = ExecutionRepository()
        self.media_repo = MediaRepository()
        self.market_data_repo = MarketDataRepository()
        self.media_service = MediaService()
        self.manifest_schema = BackupManifestSchema()

    def export_backup(self, user_id: str) -> tuple[BytesIO, str]:
        """Build a ZIP archive for the authenticated user's data."""
        payload = self._build_export_payload(user_id)
        manifest = self._build_manifest(payload)
        archive_buffer = BytesIO()

        with zipfile.ZipFile(
            archive_buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            archive.writestr(
                MANIFEST_PATH,
                json.dumps(manifest, indent=2).encode("utf-8"),
            )
            archive.writestr(
                DATA_PATH,
                json_util.dumps(payload, indent=2).encode("utf-8"),
            )
            self._write_media_files(archive, payload["media"])
            self._write_market_data_files(
                archive,
                payload["market_data_datasets"],
            )

        archive_buffer.seek(0)
        filename = (
            f"janusedge-backup-"
            f"{manifest['created_at'].replace(':', '').replace('-', '')}"
            ".zip"
        )
        return archive_buffer, filename

    def restore_backup(self, user_id: str, archive_file) -> dict:
        """Restore a portable archive into the authenticated user."""
        archive_bytes = archive_file.read()
        if not archive_bytes:
            raise ValidationError("Backup archive is empty.")

        (
            manifest,
            payload,
            media_bytes,
            market_data_bytes,
        ) = self._load_archive(
            archive_bytes
        )
        del manifest

        destination_user = self.user_repo.find_by_id(user_id)
        if not destination_user:
            raise ValidationError("Destination user not found.")

        destination_user_id = ObjectId(user_id)
        self._validate_portable_settings(payload["settings"])
        restored_symbol_mappings = (
            get_effective_symbol_mappings(
                payload["settings"].get("symbol_mappings")
            )
            if "symbol_mappings" in payload["settings"]
            else get_effective_symbol_mappings(
                destination_user.get("symbol_mappings")
            )
        )
        restored_market_data_mappings = (
            get_effective_market_data_mappings(
                payload["settings"].get("market_data_mappings")
            )
            if "market_data_mappings" in payload["settings"]
            else get_effective_market_data_mappings(
                destination_user.get("market_data_mappings")
            )
        )
        self.user_repo.update_portable_settings(
            user_id=user_id,
            timezone=payload["settings"].get(
                "timezone", destination_user["timezone"]
            ),
            display_timezone=payload["settings"].get(
                "display_timezone",
                destination_user.get(
                    "display_timezone",
                    destination_user["timezone"],
                ),
            ),
            starting_equity=payload["settings"].get(
                "starting_equity",
                destination_user.get(
                    "starting_equity",
                    DEFAULT_STARTING_EQUITY,
                ),
            ),
            risk_breakeven_enabled=payload["settings"].get(
                "risk_breakeven_enabled",
                False,
            ),
            risk_breakeven_r_threshold=payload["settings"].get(
                "risk_breakeven_r_threshold",
                DEFAULT_RISK_BREAKEVEN_R_THRESHOLD,
            ),
            symbol_mappings=restored_symbol_mappings,
            market_data_mappings=restored_market_data_mappings,
        )

        settings_updated = [
            "timezone",
            "display_timezone",
            "starting_equity",
        ]
        if "symbol_mappings" in payload["settings"]:
            settings_updated.append("symbol_mappings")
        if "market_data_mappings" in payload["settings"]:
            settings_updated.append("market_data_mappings")
        if "risk_breakeven_enabled" in payload["settings"]:
            settings_updated.append("risk_breakeven_enabled")
        if "risk_breakeven_r_threshold" in payload["settings"]:
            settings_updated.append("risk_breakeven_r_threshold")

        summary = {
            "accounts": {"created": 0, "reused": 0},
            "tags": {"created": 0, "reused": 0},
            "import_batches": {
                "created": 0,
                "reused": 0,
            },
            "trades": {"created": 0, "skipped": 0},
            "executions": {"created": 0, "skipped": 0},
            "media": {"created": 0, "skipped": 0},
            "backtest_runs": {"created": 0, "reused": 0},
            "market_data_datasets": {
                "upserted": 0,
                "objects_restored": 0,
            },
            "settings": {"updated": settings_updated},
        }

        backtest_data = payload.get("backtests") or self._empty_backtest_payload()
        backtest_run_id_map, reused_run_sources = self._prepare_backtest_run_ids(
            destination_user_id,
            backtest_data["runs"],
        )

        account_id_map = self._restore_accounts(
            destination_user_id,
            payload["accounts"],
            summary,
            backtest_run_id_map=backtest_run_id_map,
        )
        created_run_sources = self._restore_backtest_runs(
            destination_user_id,
            backtest_data["runs"],
            backtest_run_id_map,
            account_id_map,
            summary,
            reused_run_sources,
        )
        tag_id_map = self._restore_tags(
            destination_user_id,
            payload["tags"],
            summary,
        )
        batch_id_map = self._restore_import_batches(
            destination_user_id,
            payload["import_batches"],
            summary,
        )

        existing_trade_fingerprints = set(
            self.trade_repo.find_active_fingerprints(user_id)
        )
        trade_id_map = self._restore_trades(
            destination_user_id,
            payload["trades"],
            account_id_map,
            tag_id_map,
            batch_id_map,
            existing_trade_fingerprints,
            summary,
            backtest_run_id_map=backtest_run_id_map,
            reused_run_sources=reused_run_sources,
            backtest_run_docs=backtest_data["runs"],
        )
        self._reserve_open_position_trade_ids(
            backtest_data.get("simulation_positions", []),
            trade_id_map,
            created_run_sources,
        )

        execution_id_map = self._restore_executions(
            destination_user_id,
            payload["executions"],
            trade_id_map,
            account_id_map,
            batch_id_map,
            summary,
            backtest_run_id_map=backtest_run_id_map,
            reused_run_sources=reused_run_sources,
        )
        self._restore_backtest_children(
            destination_user_id,
            backtest_data,
            backtest_run_id_map,
            account_id_map,
            trade_id_map,
            execution_id_map,
            created_run_sources,
        )
        self._restore_media(
            user_id,
            payload["media"],
            trade_id_map,
            media_bytes,
            summary,
            reused_backtest_trade_sources=self._reused_backtest_trade_sources(
                payload["trades"], reused_run_sources
            ),
        )
        self._restore_market_data(
            payload["market_data_datasets"],
            market_data_bytes,
            summary,
        )

        return {
            "message": "Backup restored successfully.",
            "summary": summary,
        }

    def _build_export_payload(self, user_id: str) -> dict:
        """Collect the authenticated user's portable backup payload."""
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise ValidationError("User not found.")

        trades = self.trade_repo.find_exportable_by_user(user_id)
        backtests = self._collect_backtest_data(user_id)
        exportable_run_ids = {
            run["_id"] for run in backtests["runs"]
        }
        trades = [
            trade
            for trade in trades
            if trade.get("backtest_run_id") is None
            or trade.get("backtest_run_id") in exportable_run_ids
        ]
        runs_by_id = {run["_id"]: run for run in backtests["runs"]}
        for trade in trades:
            run_id = trade.get("backtest_run_id")
            if run_id is None:
                continue
            run = runs_by_id.get(run_id)
            if run is None:
                continue
            origin = run["portable_origin"]
            portable_trade = trade.get("portable_backup_source") or {}
            trade["portable_backup_source"] = {
                "source_user_id": str(
                    portable_trade.get("source_user_id", origin["source_user_id"])
                ),
                "source_run_id": str(
                    portable_trade.get("source_run_id", origin["source_run_id"])
                ),
                "source_trade_id": str(
                    portable_trade.get("source_trade_id", trade["_id"])
                ),
            }
        trade_ids = [trade["_id"] for trade in trades]
        executions_by_id = {
            str(execution["_id"]): execution
            for execution in self.execution_repo.find_by_trade_ids(trade_ids)
        }
        runs_by_id = {run["_id"]: run for run in backtests["runs"]}
        for execution_id, execution in list(executions_by_id.items()):
            source_run_id = execution.get("backtest_run_id")
            if source_run_id is None:
                continue
            run = runs_by_id.get(source_run_id)
            committed_sequence = int(
                ((run or {}).get("simulation_control") or {}).get(
                    "committed_sequence", 0
                )
            )
            if (
                run is None
                or execution.get("simulation_committed") is not True
                or int(execution.get("simulation_operation_sequence", 0))
                > committed_sequence
            ):
                executions_by_id.pop(execution_id, None)
        if runs_by_id:
            for execution in mongo.db.executions.find(
                {
                    "user_id": ObjectId(user_id),
                    "backtest_run_id": {"$in": list(runs_by_id)},
                    "simulation_committed": True,
                }
            ):
                run = runs_by_id.get(execution.get("backtest_run_id"))
                if run is None:
                    continue
                committed_sequence = int(
                    (run.get("simulation_control") or {}).get(
                        "committed_sequence", 0
                    )
                )
                if int(execution.get("simulation_operation_sequence", 0)) <= committed_sequence:
                    executions_by_id[str(execution["_id"])] = execution
        executions = list(executions_by_id.values())
        media_docs = self.media_repo.find_by_trade_ids(
            trade_ids
        )
        referenced_batch_ids = {
            batch_id
            for batch_id in self._iter_values(
                [trade.get("import_batch_id") for trade in trades]
                + [
                    execution.get("import_batch_id")
                    for execution in executions
                ]
            )
            if batch_id is not None
        }

        payload_media = []
        for media_doc in media_docs:
            media_copy = deepcopy(media_doc)
            media_copy["archive_path"] = (
                f"{MEDIA_PREFIX}/{str(media_doc['_id'])}/"
                f"{self._sanitize_filename(media_doc['original_filename'])}"
            )
            payload_media.append(media_copy)

        return {
            "settings": {
                "timezone": user.get("timezone"),
                "display_timezone": user.get(
                    "display_timezone",
                    user.get("timezone"),
                ),
                "starting_equity": user.get(
                    "starting_equity", DEFAULT_STARTING_EQUITY
                ),
                "risk_breakeven_enabled": (
                    bool(user.get("risk_breakeven_enabled", False))
                    if "risk_breakeven_r_threshold" in user
                    else False
                ),
                "risk_breakeven_r_threshold": user.get(
                    "risk_breakeven_r_threshold",
                    DEFAULT_RISK_BREAKEVEN_R_THRESHOLD,
                ),
                "symbol_mappings": (
                    get_effective_symbol_mappings(
                        user.get("symbol_mappings")
                    )
                ),
                "market_data_mappings": (
                    get_effective_market_data_mappings(
                        user.get("market_data_mappings")
                    )
                ),
            },
            "accounts": [
                account
                for account in self.account_repo.find_by_user(user_id)
                if account.get("backtest_run_id") is None
                or account.get("backtest_run_id") in exportable_run_ids
            ],
            "tags": self.tag_repo.find_by_user(user_id),
            "import_batches": self.batch_repo.find_by_ids(
                referenced_batch_ids
            ),
            "trades": trades,
            "executions": executions,
            "media": payload_media,
            "market_data_datasets": self._collect_market_data(
                get_effective_market_data_mappings(
                    user.get("market_data_mappings")
                )
            ),
            "backtests": backtests,
        }

    @staticmethod
    def _empty_backtest_payload() -> dict:
        """Return the stable 1.1 backtest payload shape."""
        return {
            "runs": [],
            "simulation_operations": [],
            "simulation_orders": [],
            "simulation_positions": [],
            "simulation_cost_profiles": [],
            "chart_tabs": [],
            "chart_workspaces": [],
            "drawing_states": [],
        }

    def _collect_backtest_data(self, user_id: str) -> dict:
        """Export ready runs and only the simulation records they committed."""
        user_oid = ObjectId(user_id)
        runs = list(
            mongo.db.backtest_runs.find(
                {
                    "user_id": user_oid,
                    "status": {"$in": ["ready", "complete"]},
                    "snapshot": {"$ne": None},
                }
            )
        )
        runs_by_id = {}
        portable_runs = []
        committed_by_run = {}
        for run in runs:
            origin = run.get("portable_origin") or {}
            if not origin.get("source_user_id") or not origin.get("source_run_id"):
                origin = {
                    "source_user_id": str(user_id),
                    "source_run_id": str(run["_id"]),
                }
            else:
                origin = {
                    "source_user_id": str(origin["source_user_id"]),
                    "source_run_id": str(origin["source_run_id"]),
                }
            committed = int(
                (run.get("simulation_control") or {}).get(
                    "committed_sequence", 0
                )
            )
            committed_by_run[run["_id"]] = committed
            portable = deepcopy(run)
            portable["portable_origin"] = origin
            if isinstance(portable.get("snapshot"), dict):
                portable["snapshot"] = self._portable_snapshot(
                    portable["snapshot"]
                )
            for transient in (
                "preparation_job_id",
                "preparation_lease_owner",
                "preparation_lease_expires_at",
                "deletion_lease_owner",
                "deletion_lease_expires_at",
                "cache_recovery",
                "cache_refreshed_at",
                "progress",
            ):
                portable.pop(transient, None)
            control = deepcopy(portable.get("simulation_control") or {})
            control["committed_sequence"] = committed
            control["pending_operation_id"] = None
            portable["simulation_control"] = control
            runs_by_id[run["_id"]] = portable
            portable_runs.append(portable)

        run_ids = list(runs_by_id)
        if not run_ids:
            return self._empty_backtest_payload()

        def scoped_records(collection_name: str) -> list[dict]:
            return list(
                mongo.db[collection_name].find(
                    {"user_id": user_oid, "run_id": {"$in": run_ids}}
                )
            )

        operations = [
            item
            for item in scoped_records("backtest_simulation_operations")
            if int(item.get("sequence", -1))
            <= committed_by_run.get(item.get("run_id"), -1)
            and item.get("state") in {"committed", "rejected"}
            and item.get("final_state", item.get("state"))
            in {"committed", "rejected"}
        ]
        orders = [
            item
            for item in scoped_records("backtest_simulation_orders")
            if int(item.get("operation_sequence", -1))
            <= committed_by_run.get(item.get("run_id"), -1)
        ]
        positions = [
            item
            for item in scoped_records("backtest_simulation_positions")
            if int(item.get("operation_sequence", -1))
            <= committed_by_run.get(item.get("run_id"), -1)
        ]
        cost_profiles = [
            item
            for item in scoped_records("backtest_simulation_cost_profiles")
            if int(item.get("operation_sequence", -1))
            <= committed_by_run.get(item.get("run_id"), -1)
        ]

        return {
            "runs": portable_runs,
            "simulation_operations": operations,
            "simulation_orders": orders,
            "simulation_positions": positions,
            "simulation_cost_profiles": cost_profiles,
            "chart_tabs": scoped_records("backtest_chart_tabs"),
            "chart_workspaces": scoped_records("backtest_chart_workspaces"),
            "drawing_states": scoped_records("backtest_drawing_states"),
        }

    @classmethod
    def _portable_snapshot(cls, value):
        """Strip source-specific object keys while keeping cache-day manifests."""
        if isinstance(value, list):
            return [cls._portable_snapshot(item) for item in value]
        if not isinstance(value, dict):
            return deepcopy(value)

        if (
            value.get("instrument")
            and value.get("utc_date")
            and any(key in value for key in ("sha256", "candle_count", "cache_key"))
        ):
            allowed = (
                "cache_version",
                "instrument",
                "utc_date",
                "sha256",
                "outcome",
                "candle_count",
            )
            return {
                key: deepcopy(value[key])
                for key in allowed
                if key in value
            }

        return {
            key: cls._portable_snapshot(item)
            for key, item in value.items()
            if key not in {"object_key", "source_object_key", "cache_key"}
        }

    def _prepare_backtest_run_ids(
        self, destination_user_id: ObjectId, run_docs: List[dict]
    ) -> tuple[dict[str, ObjectId], set[str]]:
        """Map portable source run identities to existing or new run IDs."""
        run_id_map: dict[str, ObjectId] = {}
        reused_sources: set[str] = set()
        for source_doc in run_docs:
            source_id = str(source_doc["_id"])
            origin = source_doc["portable_origin"]
            existing = mongo.db.backtest_runs.find_one(
                {
                    "user_id": destination_user_id,
                    "portable_origin.source_user_id": str(
                        origin["source_user_id"]
                    ),
                    "portable_origin.source_run_id": str(
                        origin["source_run_id"]
                    ),
                }
            )
            if existing:
                run_id_map[source_id] = existing["_id"]
                reused_sources.add(source_id)
            else:
                run_id_map[source_id] = ObjectId()
        return run_id_map, reused_sources

    def _bind_snapshot_cache(self, snapshot: dict, user_id: ObjectId) -> tuple[dict, bool]:
        """Bind portable cache-day manifests to exact destination cache refs."""
        cache = BacktestCandleCache()
        resolved: dict[tuple[str, str], dict | None] = {}
        has_missing = False

        def resolve(ref: dict) -> dict:
            nonlocal has_missing
            key = (str(ref.get("instrument", "")).upper(), str(ref.get("utc_date", "")))
            if key not in resolved:
                destination_ref = None
                try:
                    from datetime import date

                    destination_ref = cache.get_reference(
                        user_id=user_id,
                        instrument=key[0],
                        utc_date=date.fromisoformat(key[1]),
                    )
                except (ValueError, KeyError, RuntimeError):
                    destination_ref = None
                matches = (
                    destination_ref is not None
                    and destination_ref.get("cache_version") == ref.get("cache_version")
                    and destination_ref.get("sha256") == ref.get("sha256")
                    and destination_ref.get("outcome") == ref.get("outcome")
                    and destination_ref.get("candle_count") == ref.get("candle_count")
                    and all(key)
                )
                resolved[key] = destination_ref if matches else None
                if not matches:
                    has_missing = True
            destination_ref = resolved[key]
            if destination_ref is not None:
                return destination_ref
            return {
                key: deepcopy(ref[key])
                for key in (
                    "cache_version",
                    "instrument",
                    "utc_date",
                    "sha256",
                    "outcome",
                    "candle_count",
                )
                if key in ref
            }

        def walk(value):
            if isinstance(value, list):
                return [walk(item) for item in value]
            if not isinstance(value, dict):
                return deepcopy(value)
            if (
                value.get("instrument")
                and value.get("utc_date")
                and any(key in value for key in ("sha256", "candle_count"))
            ):
                return resolve(value)
            return {
                key: walk(item)
                for key, item in value.items()
                if key not in {"object_key", "source_object_key", "cache_key"}
            }

        return walk(snapshot), has_missing

    def _restore_backtest_runs(
        self,
        destination_user_id: ObjectId,
        run_docs: List[dict],
        run_id_map: dict[str, ObjectId],
        account_id_map: dict[str, ObjectId],
        summary: dict,
        reused_sources: set[str],
    ) -> set[str]:
        """Insert new run metadata and bind its destination candle cache."""
        created_sources = set()
        for source_doc in run_docs:
            source_id = str(source_doc["_id"])
            if source_id in reused_sources:
                summary["backtest_runs"]["reused"] += 1
                continue

            run_id = run_id_map[source_id]
            new_doc = deepcopy(source_doc)
            new_doc["_id"] = run_id
            new_doc["user_id"] = destination_user_id
            source_account_id = source_doc.get("account_id")
            new_doc["account_id"] = (
                account_id_map.get(str(source_account_id))
                if source_account_id is not None
                else None
            )
            snapshot = source_doc.get("snapshot")
            if isinstance(snapshot, dict):
                new_doc["snapshot"], missing = self._bind_snapshot_cache(
                    snapshot, destination_user_id
                )
            else:
                missing = True
            new_doc["cache_availability"] = "missing" if missing else "available"
            new_doc["cache_recovery"] = {
                "state": "idle",
                "missing_references": [],
                "completed": 0,
                "total": 0,
            }
            new_doc.pop("cache_refreshed_at", None)
            control = deepcopy(new_doc.get("simulation_control") or {})
            control["pending_operation_id"] = None
            new_doc["simulation_control"] = control
            for transient in (
                "preparation_job_id",
                "preparation_lease_owner",
                "preparation_lease_expires_at",
                "deletion_lease_owner",
                "deletion_lease_expires_at",
                "progress",
            ):
                new_doc.pop(transient, None)
            try:
                mongo.db.backtest_runs.insert_one(new_doc)
            except Exception as exc:
                # A unique portable-origin index makes concurrent restores
                # converge on the run inserted by the other request.
                from pymongo.errors import DuplicateKeyError

                if not isinstance(exc, DuplicateKeyError):
                    raise
                origin = source_doc["portable_origin"]
                existing = mongo.db.backtest_runs.find_one(
                    {
                        "user_id": destination_user_id,
                        "portable_origin.source_user_id": origin["source_user_id"],
                        "portable_origin.source_run_id": origin["source_run_id"],
                    }
                )
                if existing is None:
                    raise
                mongo.db.trade_accounts.update_many(
                    {
                        "user_id": destination_user_id,
                        "backtest_run_id": run_id,
                    },
                    {"$set": {"backtest_run_id": existing["_id"]}},
                )
                run_id_map[source_id] = existing["_id"]
                reused_sources.add(source_id)
                summary["backtest_runs"]["reused"] += 1
                continue
            created_sources.add(source_id)
            summary["backtest_runs"]["created"] += 1
        return created_sources

    @staticmethod
    def _reused_backtest_trade_sources(
        trade_docs: List[dict], reused_run_sources: set[str]
    ) -> set[str]:
        """Identify source trades whose run graph was already restored."""
        return {
            str(trade["_id"])
            for trade in trade_docs
            if trade.get("backtest_run_id") is not None
            and str(trade["backtest_run_id"]) in reused_run_sources
        }

    @staticmethod
    def _reserve_open_position_trade_ids(
        position_docs: List[dict],
        trade_id_map: dict[str, ObjectId],
        created_run_sources: set[str],
    ) -> None:
        """Preserve future trade IDs for positions without a trade document.

        A simulated trade is published to the trades collection only after its
        position closes. Until then, committed fills and the position already
        refer to the future trade ID. Reserve a destination ID for that link so
        the close operation can later publish its trade under the same ID.
        """
        for position in position_docs:
            source_run_id = position.get("run_id")
            if (
                source_run_id is None
                or str(source_run_id) not in created_run_sources
            ):
                continue
            source_trade_id = position.get("simulated_trade_id")
            if source_trade_id is not None:
                trade_id_map.setdefault(str(source_trade_id), ObjectId())

    def _build_manifest(self, payload: dict) -> dict:
        """Create the backup manifest metadata."""
        from app.utils.datetime_utils import utc_now

        return {
            "archive_type": BACKUP_ARCHIVE_TYPE,
            "version": BACKUP_ARCHIVE_VERSION,
            "created_at": utc_now().isoformat(),
            "counts": {
                "accounts": len(payload["accounts"]),
                "tags": len(payload["tags"]),
                "import_batches": len(payload["import_batches"]),
                "trades": len(payload["trades"]),
                "executions": len(payload["executions"]),
                "media": len(payload["media"]),
                "market_data_datasets": len(
                    payload["market_data_datasets"]
                ),
                "backtest_runs": len(payload.get("backtests", {}).get("runs", [])),
            },
        }

    def _write_market_data_files(
        self,
        archive: zipfile.ZipFile,
        dataset_docs: List[dict],
    ) -> None:
        """Write Parquet market-data objects into the ZIP archive."""

        if not dataset_docs:
            return

        client = get_client()
        bucket = get_market_data_bucket()

        for dataset_doc in dataset_docs:
            response = client.get_object(
                bucket,
                dataset_doc.get(
                    "source_object_key",
                    dataset_doc["object_key"],
                ),
            )
            try:
                archive.writestr(
                    dataset_doc["archive_path"],
                    response.read(),
                )
            finally:
                if hasattr(response, "close"):
                    response.close()
                if hasattr(response, "release_conn"):
                    response.release_conn()

    def _write_media_files(
        self, archive: zipfile.ZipFile, media_docs: List[dict]
    ) -> None:
        """Write media binaries into the ZIP archive."""
        if not media_docs:
            return

        client = get_client()
        bucket = get_bucket()

        for media_doc in media_docs:
            response = client.get_object(
                bucket, media_doc["object_key"]
            )
            try:
                archive.writestr(
                    media_doc["archive_path"],
                    response.read(),
                )
            finally:
                if hasattr(response, "close"):
                    response.close()
                if hasattr(response, "release_conn"):
                    response.release_conn()

    def _load_archive(
        self, archive_bytes: bytes
    ) -> tuple[dict, dict, dict[str, bytes], dict[str, bytes]]:
        """Load and validate the ZIP archive contents."""
        try:
            archive = zipfile.ZipFile(BytesIO(archive_bytes))
        except zipfile.BadZipFile as exc:
            raise ValidationError(
                "Invalid backup archive."
            ) from exc

        with archive:
            names = set(archive.namelist())
            if MANIFEST_PATH not in names or DATA_PATH not in names:
                raise ValidationError(
                    "Backup archive is missing required files."
                )

            try:
                manifest = json.loads(
                    archive.read(MANIFEST_PATH).decode("utf-8")
                )
                payload = json_util.loads(
                    archive.read(DATA_PATH).decode("utf-8")
                )
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValidationError(
                    "Backup archive metadata is invalid."
                ) from exc

            try:
                validated_manifest = self.manifest_schema.load(
                    manifest
                )
            except Exception as exc:
                raise ValidationError(
                    "Backup manifest is invalid."
                ) from exc

            archive_version = validated_manifest["version"]
            if validated_manifest["archive_type"] != BACKUP_ARCHIVE_TYPE:
                raise ValidationError(
                    "Backup archive version is not supported."
                )

            if archive_version == "1.0":
                payload.setdefault("backtests", self._empty_backtest_payload())
            self._validate_payload_structure(payload, archive_version)

            media_bytes: dict[str, bytes] = {}
            for media_doc in payload["media"]:
                archive_path = media_doc.get("archive_path")
                if not archive_path or archive_path not in names:
                    raise ValidationError(
                        "Backup archive media content is incomplete."
                    )
                media_bytes[archive_path] = archive.read(
                    archive_path
                )

            market_data_bytes: dict[str, bytes] = {}
            for dataset_doc in payload["market_data_datasets"]:
                archive_path = dataset_doc.get("archive_path")
                if not archive_path or archive_path not in names:
                    raise ValidationError(
                        "Backup archive market-data content is incomplete."
                    )
                market_data_bytes[archive_path] = archive.read(
                    archive_path
                )

            return (
                validated_manifest,
                payload,
                media_bytes,
                market_data_bytes,
            )

    def _validate_payload_structure(
        self, payload: dict, archive_version: str = "1.0"
    ) -> None:
        """Validate the data payload shape before restore."""
        required_keys = {
            "settings",
            "accounts",
            "tags",
            "import_batches",
            "trades",
            "executions",
            "media",
            "market_data_datasets",
        }
        if not isinstance(payload, dict) or not required_keys.issubset(
            payload
        ):
            raise ValidationError(
                "Backup archive payload is invalid."
            )

        self._validate_portable_settings(payload["settings"])
        backtests = payload.get("backtests")
        if archive_version == "1.1" and not isinstance(backtests, dict):
            raise ValidationError("Backup archive backtest payload is invalid.")
        if backtests is not None:
            expected = set(self._empty_backtest_payload())
            if (
                not isinstance(backtests, dict)
                or not expected.issubset(backtests)
                or any(not isinstance(backtests[key], list) for key in expected)
            ):
                raise ValidationError("Backup archive backtest payload is invalid.")
            run_ids = set()
            origins = set()
            for run in backtests["runs"]:
                if not isinstance(run, dict) or "_id" not in run:
                    raise ValidationError("Backup archive backtest run is invalid.")
                source_run_id = str(run["_id"])
                if source_run_id in run_ids:
                    raise ValidationError("Backup archive has duplicate backtest runs.")
                run_ids.add(source_run_id)
                origin = run.get("portable_origin")
                if not isinstance(origin, dict) or not origin.get("source_user_id") or not origin.get("source_run_id"):
                    raise ValidationError("Backup archive backtest run identity is invalid.")
                origin_key = (str(origin["source_user_id"]), str(origin["source_run_id"]))
                if origin_key in origins:
                    raise ValidationError("Backup archive has duplicate backtest run identities.")
                origins.add(origin_key)

            for key in expected - {"runs"}:
                for document in backtests[key]:
                    if not isinstance(document, dict) or "run_id" not in document:
                        raise ValidationError("Backup archive backtest records are invalid.")
                    if str(document["run_id"]) not in run_ids:
                        raise ValidationError("Backup archive backtest record has an unknown run.")

    def _validate_portable_settings(self, settings: dict) -> None:
        """Validate portable settings that may be restored."""
        if not isinstance(settings, dict):
            raise ValidationError(
                "Backup archive settings payload is invalid."
            )

        timezone_value = settings.get("timezone")
        display_timezone = settings.get("display_timezone")
        starting_equity = settings.get("starting_equity")

        if not timezone_value or not is_valid_timezone(
            timezone_value
        ):
            raise ValidationError(
                "Backup archive contains an invalid timezone."
            )
        if not display_timezone or not is_valid_timezone(
            display_timezone
        ):
            raise ValidationError(
                "Backup archive contains an invalid display timezone."
            )
        if starting_equity is None or float(starting_equity) < 0:
            raise ValidationError(
                "Backup archive contains an invalid starting equity."
            )

        risk_breakeven_enabled = settings.get(
            "risk_breakeven_enabled"
        )
        if (
            risk_breakeven_enabled is not None
            and not isinstance(risk_breakeven_enabled, bool)
        ):
            raise ValidationError(
                "Backup archive contains an invalid risk breakeven setting."
            )

        risk_breakeven_r_threshold = settings.get(
            "risk_breakeven_r_threshold"
        )
        if risk_breakeven_r_threshold is not None:
            try:
                threshold = float(risk_breakeven_r_threshold)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    "Backup archive contains an invalid risk breakeven threshold."
                ) from exc
            if threshold < 0:
                raise ValidationError(
                    "Backup archive contains an invalid risk breakeven threshold."
                )

        symbol_mappings = settings.get("symbol_mappings")
        if symbol_mappings is not None:
            try:
                validate_symbol_mappings(symbol_mappings)
            except ValueError as exc:
                raise ValidationError(
                    "Backup archive contains invalid symbol mappings."
                ) from exc

        market_data_mappings = settings.get(
            "market_data_mappings"
        )
        if market_data_mappings is not None:
            try:
                validate_market_data_mappings(
                    market_data_mappings
                )
            except ValueError as exc:
                raise ValidationError(
                    "Backup archive contains invalid market data mappings."
                ) from exc

    def _restore_accounts(
        self,
        destination_user_id: ObjectId,
        account_docs: List[dict],
        summary: dict,
        *,
        backtest_run_id_map: dict[str, ObjectId] | None = None,
    ) -> dict[str, ObjectId]:
        """Restore accounts using account name as the natural key."""
        backtest_run_id_map = backtest_run_id_map or {}
        account_id_map: dict[str, ObjectId] = {}
        for source_doc in account_docs:
            source_run_id = source_doc.get("backtest_run_id")
            if source_run_id is not None:
                destination_run_id = backtest_run_id_map.get(str(source_run_id))
                if destination_run_id is None:
                    continue
                account_query = {
                    "user_id": destination_user_id,
                    "backtest_run_id": destination_run_id,
                }
            else:
                account_query = {
                    "user_id": destination_user_id,
                    "account_name": source_doc["account_name"],
                }
            existing = self.account_repo.find_one(account_query)
            if existing:
                summary["accounts"]["reused"] += 1
                account_id_map[str(source_doc["_id"])] = existing[
                    "_id"
                ]
                continue

            new_doc = deepcopy(source_doc)
            new_id = ObjectId()
            new_doc["_id"] = new_id
            new_doc["user_id"] = destination_user_id
            if source_run_id is not None:
                new_doc["backtest_run_id"] = destination_run_id
            self.account_repo.insert_one(new_doc)
            summary["accounts"]["created"] += 1
            account_id_map[str(source_doc["_id"])] = new_id
        return account_id_map

    def _restore_tags(
        self,
        destination_user_id: ObjectId,
        tag_docs: List[dict],
        summary: dict,
    ) -> dict[str, ObjectId]:
        """Restore tags using tag name as the natural key."""
        tag_id_map: dict[str, ObjectId] = {}
        for source_doc in tag_docs:
            existing = self.tag_repo.find_one(
                {
                    "user_id": destination_user_id,
                    "name": source_doc["name"],
                }
            )
            if existing:
                summary["tags"]["reused"] += 1
                tag_id_map[str(source_doc["_id"])] = existing[
                    "_id"
                ]
                continue

            new_doc = deepcopy(source_doc)
            new_id = ObjectId()
            new_doc["_id"] = new_id
            new_doc["user_id"] = destination_user_id
            self.tag_repo.insert_one(new_doc)
            summary["tags"]["created"] += 1
            tag_id_map[str(source_doc["_id"])] = new_id
        return tag_id_map

    def _restore_import_batches(
        self,
        destination_user_id: ObjectId,
        batch_docs: List[dict],
        summary: dict,
    ) -> dict[str, ObjectId]:
        """Restore import batches using file hash as the natural key."""
        batch_id_map: dict[str, ObjectId] = {}
        for source_doc in batch_docs:
            existing = self.batch_repo.find_one(
                {
                    "user_id": destination_user_id,
                    "file_hash": source_doc["file_hash"],
                }
            )
            if existing:
                summary["import_batches"]["reused"] += 1
                batch_id_map[str(source_doc["_id"])] = existing[
                    "_id"
                ]
                continue

            new_doc = deepcopy(source_doc)
            new_id = ObjectId()
            new_doc["_id"] = new_id
            new_doc["user_id"] = destination_user_id
            self.batch_repo.insert_one(new_doc)
            summary["import_batches"]["created"] += 1
            batch_id_map[str(source_doc["_id"])] = new_id
        return batch_id_map

    def _restore_trades(
        self,
        destination_user_id: ObjectId,
        trade_docs: List[dict],
        account_id_map: dict[str, ObjectId],
        tag_id_map: dict[str, ObjectId],
        batch_id_map: dict[str, ObjectId],
        existing_trade_fingerprints: set[str],
        summary: dict,
        *,
        backtest_run_id_map: dict[str, ObjectId] | None = None,
        reused_run_sources: set[str] | None = None,
        backtest_run_docs: List[dict] | None = None,
    ) -> dict[str, ObjectId]:
        """Restore trades and skip duplicates by stable fingerprint."""
        backtest_run_id_map = backtest_run_id_map or {}
        reused_run_sources = reused_run_sources or set()
        run_docs_by_source_id = {
            str(run["_id"]): run for run in (backtest_run_docs or [])
        }
        trade_id_map: dict[str, ObjectId] = {}
        for source_doc in trade_docs:
            source_run_id = source_doc.get("backtest_run_id")
            if source_run_id is not None:
                source_run_id_text = str(source_run_id)
                destination_run_id = backtest_run_id_map.get(source_run_id_text)
                if destination_run_id is None:
                    summary["trades"]["skipped"] += 1
                    continue
                source_run = run_docs_by_source_id.get(source_run_id_text)
                origin = (source_run or {}).get("portable_origin") or {}
                portable_identity = source_doc.get("portable_backup_source") or {
                    "source_user_id": str(origin.get("source_user_id", "")),
                    "source_run_id": str(origin.get("source_run_id", "")),
                    "source_trade_id": str(source_doc["_id"]),
                }
                identity_query = {
                    "user_id": destination_user_id,
                    "backtest_run_id": destination_run_id,
                    "portable_backup_source.source_user_id": str(
                        portable_identity.get("source_user_id", "")
                    ),
                    "portable_backup_source.source_run_id": str(
                        portable_identity.get("source_run_id", "")
                    ),
                    "portable_backup_source.source_trade_id": str(
                        portable_identity.get("source_trade_id", "")
                    ),
                }
                existing_backtest_trade = mongo.db.trades.find_one(identity_query)
                if existing_backtest_trade:
                    trade_id_map[str(source_doc["_id"])] = existing_backtest_trade["_id"]
                    summary["trades"]["skipped"] += 1
                    continue
                if source_run_id_text in reused_run_sources:
                    summary["trades"]["skipped"] += 1
                    continue

                new_doc = deepcopy(source_doc)
                source_id = str(source_doc["_id"])
                new_id = ObjectId()
                new_doc["_id"] = new_id
                new_doc["user_id"] = destination_user_id
                new_doc["backtest_run_id"] = destination_run_id
                new_doc["trade_account_id"] = account_id_map[
                    str(source_doc["trade_account_id"])
                ]
                new_doc["portable_backup_source"] = {
                    "source_user_id": str(portable_identity["source_user_id"]),
                    "source_run_id": str(portable_identity["source_run_id"]),
                    "source_trade_id": str(portable_identity["source_trade_id"]),
                }
                import_batch_id = source_doc.get("import_batch_id")
                new_doc["import_batch_id"] = (
                    batch_id_map[str(import_batch_id)]
                    if import_batch_id is not None
                    else None
                )
                new_doc["tag_ids"] = [
                    tag_id_map[str(tag_id)]
                    for tag_id in source_doc.get("tag_ids", [])
                    if str(tag_id) in tag_id_map
                ]
                self.trade_repo.insert_one(new_doc)
                trade_id_map[source_id] = new_id
                summary["trades"]["created"] += 1
                continue

            fingerprint = build_trade_fingerprint(source_doc)
            if fingerprint in existing_trade_fingerprints:
                summary["trades"]["skipped"] += 1
                continue

            new_doc = deepcopy(source_doc)
            source_id = str(source_doc["_id"])
            new_id = ObjectId()
            new_doc["_id"] = new_id
            new_doc["user_id"] = destination_user_id
            new_doc["trade_account_id"] = account_id_map[
                str(source_doc["trade_account_id"])
            ]
            import_batch_id = source_doc.get("import_batch_id")
            new_doc["import_batch_id"] = (
                batch_id_map[str(import_batch_id)]
                if import_batch_id is not None
                else None
            )
            new_doc["tag_ids"] = [
                tag_id_map[str(tag_id)]
                for tag_id in source_doc.get("tag_ids", [])
                if str(tag_id) in tag_id_map
            ]
            self.trade_repo.insert_one(new_doc)
            existing_trade_fingerprints.add(fingerprint)
            trade_id_map[source_id] = new_id
            summary["trades"]["created"] += 1
        return trade_id_map

    def _restore_executions(
        self,
        destination_user_id: ObjectId,
        execution_docs: List[dict],
        trade_id_map: dict[str, ObjectId],
        account_id_map: dict[str, ObjectId],
        batch_id_map: dict[str, ObjectId],
        summary: dict,
        *,
        backtest_run_id_map: dict[str, ObjectId] | None = None,
        reused_run_sources: set[str] | None = None,
    ) -> dict[str, ObjectId]:
        """Restore executions, including published fills for new backtest runs."""
        backtest_run_id_map = backtest_run_id_map or {}
        reused_run_sources = reused_run_sources or set()
        execution_id_map: dict[str, ObjectId] = {}
        for source_doc in execution_docs:
            source_run_id = source_doc.get("backtest_run_id")
            if source_run_id is not None:
                source_run_id_text = str(source_run_id)
                if source_run_id_text not in backtest_run_id_map:
                    summary["executions"]["skipped"] += 1
                    continue
                if source_run_id_text in reused_run_sources:
                    summary["executions"]["skipped"] += 1
                    continue
            source_trade_id = source_doc.get("trade_id")
            if source_trade_id is not None and str(source_trade_id) not in trade_id_map:
                summary["executions"]["skipped"] += 1
                continue
            source_account_id = source_doc.get("trade_account_id")
            if source_account_id is not None and str(source_account_id) not in account_id_map:
                summary["executions"]["skipped"] += 1
                continue

            new_doc = deepcopy(source_doc)
            new_id = ObjectId()
            new_doc["_id"] = new_id
            new_doc["user_id"] = destination_user_id
            if source_trade_id is not None:
                new_doc["trade_id"] = trade_id_map[str(source_trade_id)]
            if source_account_id is not None:
                new_doc["trade_account_id"] = account_id_map[str(source_account_id)]
            if source_run_id is not None:
                new_doc["backtest_run_id"] = backtest_run_id_map[str(source_run_id)]
            import_batch_id = source_doc.get("import_batch_id")
            new_doc["import_batch_id"] = (
                batch_id_map[str(import_batch_id)]
                if import_batch_id is not None
                else None
            )
            self.execution_repo.insert_one(new_doc)
            execution_id_map[str(source_doc["_id"])] = new_id
            summary["executions"]["created"] += 1
        return execution_id_map

    def _restore_backtest_children(
        self,
        destination_user_id: ObjectId,
        backtest_data: dict,
        run_id_map: dict[str, ObjectId],
        account_id_map: dict[str, ObjectId],
        trade_id_map: dict[str, ObjectId],
        execution_id_map: dict[str, ObjectId],
        created_run_sources: set[str],
    ) -> None:
        """Restore committed run journals, entity versions, and chart state."""
        collections = {
            "simulation_operations": "backtest_simulation_operations",
            "simulation_orders": "backtest_simulation_orders",
            "simulation_positions": "backtest_simulation_positions",
            "simulation_cost_profiles": "backtest_simulation_cost_profiles",
            "chart_tabs": "backtest_chart_tabs",
            "chart_workspaces": "backtest_chart_workspaces",
            "drawing_states": "backtest_drawing_states",
        }
        for payload_key, collection_name in collections.items():
            for source_doc in backtest_data.get(payload_key, []):
                source_run_id = str(source_doc.get("run_id"))
                if source_run_id not in created_run_sources:
                    continue
                new_doc = deepcopy(source_doc)
                new_doc["_id"] = ObjectId()
                new_doc["user_id"] = destination_user_id
                new_doc["run_id"] = run_id_map[source_run_id]

                source_account_id = new_doc.get("trade_account_id")
                if source_account_id is not None:
                    mapped_account_id = account_id_map.get(str(source_account_id))
                    if mapped_account_id is None:
                        raise ValidationError(
                            "Backup backtest state references an unknown account."
                        )
                    new_doc["trade_account_id"] = mapped_account_id

                if payload_key == "simulation_positions":
                    source_trade_id = new_doc.get("simulated_trade_id")
                    if source_trade_id is not None:
                        mapped_trade_id = trade_id_map.get(str(source_trade_id))
                        if mapped_trade_id is None:
                            raise ValidationError(
                                "Backup backtest position references an unknown trade."
                            )
                        new_doc["simulated_trade_id"] = mapped_trade_id
                    remapped_fill_ids = []
                    for source_fill_id in new_doc.get("entry_fill_ids", []):
                        mapped_fill_id = execution_id_map.get(str(source_fill_id))
                        if mapped_fill_id is None:
                            raise ValidationError(
                                "Backup backtest position references an unknown fill."
                            )
                        remapped_fill_ids.append(mapped_fill_id)
                    new_doc["entry_fill_ids"] = remapped_fill_ids

                mongo.db[collection_name].insert_one(new_doc)

    def _restore_media(
        self,
        destination_user_id: str,
        media_docs: List[dict],
        trade_id_map: dict[str, ObjectId],
        media_bytes: dict[str, bytes],
        summary: dict,
        *,
        reused_backtest_trade_sources: set[str] | None = None,
    ) -> None:
        """Restore media objects and metadata for inserted trades only."""
        client = get_client()
        bucket = get_bucket()
        ensure_bucket_exists(client, bucket)

        reused_backtest_trade_sources = reused_backtest_trade_sources or set()
        for source_doc in media_docs:
            source_trade_id = source_doc.get("trade_id")
            if str(source_trade_id) in reused_backtest_trade_sources:
                summary["media"]["skipped"] += 1
                continue
            if source_trade_id is None or str(source_trade_id) not in trade_id_map:
                summary["media"]["skipped"] += 1
                continue

            new_trade_id = str(trade_id_map[str(source_trade_id)])
            archive_path = source_doc["archive_path"]
            object_key = self.media_service._object_key(
                destination_user_id,
                new_trade_id,
                source_doc["original_filename"],
            )
            payload = media_bytes[archive_path]
            client.put_object(
                bucket,
                object_key,
                BytesIO(payload),
                length=len(payload),
                content_type=source_doc["content_type"],
            )

            new_doc = deepcopy(source_doc)
            new_doc.pop("archive_path", None)
            new_doc["_id"] = ObjectId()
            new_doc["user_id"] = ObjectId(destination_user_id)
            new_doc["trade_id"] = trade_id_map[
                str(source_trade_id)
            ]
            new_doc["object_key"] = object_key
            self.media_repo.insert_one(new_doc)
            summary["media"]["created"] += 1

    def _restore_market_data(
        self,
        market_data_docs: List[dict],
        market_data_bytes: dict[str, bytes],
        summary: dict,
    ) -> None:
        """Restore market-data metadata and referenced Parquet objects."""

        client = get_client()
        bucket = get_market_data_bucket()
        ensure_bucket_exists(client, bucket)

        for source_doc in market_data_docs:
            archive_path = source_doc["archive_path"]
            payload = market_data_bytes[archive_path]
            client.put_object(
                bucket,
                source_doc["object_key"],
                BytesIO(payload),
                length=len(payload),
                content_type="application/x-parquet",
            )

            new_doc = deepcopy(source_doc)
            new_doc.pop("archive_path", None)
            new_doc.pop("source_object_key", None)
            new_doc["_id"] = ObjectId()
            self.market_data_repo.upsert_document(new_doc)
            summary["market_data_datasets"]["upserted"] += 1
            summary["market_data_datasets"][
                "objects_restored"
            ] += 1

    def _collect_market_data(
        self,
        market_data_mappings: dict | None,
    ) -> List[dict]:
        """Collect all ready market-data datasets for portable backup."""

        datasets = self.market_data_repo.find_all_ready_documents()
        selected: dict[tuple[str, str, str | None, object], dict] = {}
        for dataset in datasets:
            storage_symbol = resolve_market_data_storage_symbol(
                dataset.get("symbol", ""),
                dataset.get("raw_symbol"),
                market_data_mappings,
            )
            if not storage_symbol:
                continue

            dataset_copy = deepcopy(dataset)
            dataset_date = dataset.get("date")
            if hasattr(dataset_date, "date"):
                dataset_date = dataset_date.date()
            dataset_copy["source_object_key"] = dataset["object_key"]
            dataset_copy["symbol"] = storage_symbol
            dataset_copy["object_key"] = (
                self._build_market_data_object_key(
                    storage_symbol,
                    dataset["dataset_type"],
                    dataset.get("timeframe"),
                    dataset_date,
                )
            )
            dataset_copy["archive_path"] = (
                f"{MARKET_DATA_PREFIX}/"
                f"{self._sanitize_filename(storage_symbol)}/"
                f"{dataset['dataset_type']}/"
                f"{self._sanitize_filename(dataset.get('timeframe') or 'raw')}/"
                f"{dataset_date.year:04d}/"
                f"{dataset_date.month:02d}/"
                f"{dataset_date.day:02d}.parquet"
            )
            key = (
                storage_symbol,
                dataset["dataset_type"],
                dataset.get("timeframe"),
                dataset_date,
            )
            existing = selected.get(key)
            if existing is None or self._prefer_market_data_export_document(
                dataset_copy,
                existing,
            ):
                selected[key] = dataset_copy

        payload = sorted(
            selected.values(),
            key=lambda dataset: (
                dataset["symbol"],
                dataset["dataset_type"],
                dataset.get("timeframe") or "",
                dataset["date"],
            ),
        )
        return payload

    @staticmethod
    def _prefer_market_data_export_document(
        candidate: dict,
        existing: dict,
    ) -> bool:
        """Choose the best document when multiple aliases map to one key."""

        candidate_exact = (
            candidate.get("source_object_key", "")
            == candidate.get("object_key", "")
        )
        existing_exact = (
            existing.get("source_object_key", "")
            == existing.get("object_key", "")
        )
        if candidate_exact != existing_exact:
            return candidate_exact

        candidate_updated = candidate.get("updated_at") or candidate.get(
            "created_at"
        )
        existing_updated = existing.get("updated_at") or existing.get(
            "created_at"
        )
        if candidate_updated != existing_updated:
            return candidate_updated > existing_updated

        return str(candidate.get("_id", "")) > str(
            existing.get("_id", "")
        )

    @staticmethod
    def _build_market_data_object_key(
        symbol: str,
        dataset_type: str,
        timeframe: str | None,
        trading_day,
    ) -> str:
        """Build the canonical object key used for backup restore."""

        safe_symbol = symbol.replace("/", "_").replace("\\", "_")
        if dataset_type == "ticks":
            return (
                f"{safe_symbol}/{dataset_type}/"
                f"{trading_day.year:04d}/{trading_day.month:02d}/"
                f"{trading_day.day:02d}.parquet"
            )
        return (
            f"{safe_symbol}/{dataset_type}/{timeframe}/"
            f"{trading_day.year:04d}/{trading_day.month:02d}/"
            f"{trading_day.day:02d}.parquet"
        )

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitize a filename for safe archive paths."""
        return filename.replace("\\", "_").replace("/", "_")

    @staticmethod
    def _iter_values(values: Iterable[Any]) -> Iterable[Any]:
        """Iterate over values while filtering out empty collections."""
        for value in values:
            if value is not None:
                yield value
