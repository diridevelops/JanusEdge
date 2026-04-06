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
from app.market_data.symbol_mapper import (
    get_effective_market_data_mappings,
    get_effective_symbol_mappings,
    resolve_market_data_storage_symbol,
    validate_market_data_mappings,
    validate_symbol_mappings,
)
from app.media.service import MediaService
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
BACKUP_ARCHIVE_VERSION = "1.0"
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
                destination_user.get("starting_equity", 10000.0),
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
            "market_data_datasets": {
                "upserted": 0,
                "objects_restored": 0,
            },
            "settings": {"updated": settings_updated},
        }

        account_id_map = self._restore_accounts(
            destination_user_id,
            payload["accounts"],
            summary,
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
        )

        self._restore_executions(
            destination_user_id,
            payload["executions"],
            trade_id_map,
            account_id_map,
            batch_id_map,
            summary,
        )
        self._restore_media(
            user_id,
            payload["media"],
            trade_id_map,
            media_bytes,
            summary,
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
        trade_ids = [trade["_id"] for trade in trades]
        executions = self.execution_repo.find_by_trade_ids(
            trade_ids
        )
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
                    "starting_equity", 10000.0
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
            "accounts": self.account_repo.find_by_user(user_id),
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
        }

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

            if (
                validated_manifest["archive_type"]
                != BACKUP_ARCHIVE_TYPE
                or validated_manifest["version"]
                != BACKUP_ARCHIVE_VERSION
            ):
                raise ValidationError(
                    "Backup archive version is not supported."
                )

            self._validate_payload_structure(payload)

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

    def _validate_payload_structure(self, payload: dict) -> None:
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
    ) -> dict[str, ObjectId]:
        """Restore accounts using account name as the natural key."""
        account_id_map: dict[str, ObjectId] = {}
        for source_doc in account_docs:
            existing = self.account_repo.find_one(
                {
                    "user_id": destination_user_id,
                    "account_name": source_doc["account_name"],
                }
            )
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
    ) -> dict[str, ObjectId]:
        """Restore trades and skip duplicates by stable fingerprint."""
        trade_id_map: dict[str, ObjectId] = {}
        for source_doc in trade_docs:
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
    ) -> None:
        """Restore executions for inserted trades only."""
        for source_doc in execution_docs:
            source_trade_id = source_doc.get("trade_id")
            if source_trade_id is None or str(source_trade_id) not in trade_id_map:
                summary["executions"]["skipped"] += 1
                continue

            new_doc = deepcopy(source_doc)
            new_doc["_id"] = ObjectId()
            new_doc["user_id"] = destination_user_id
            new_doc["trade_id"] = trade_id_map[
                str(source_trade_id)
            ]
            new_doc["trade_account_id"] = account_id_map[
                str(source_doc["trade_account_id"])
            ]
            import_batch_id = source_doc.get("import_batch_id")
            new_doc["import_batch_id"] = (
                batch_id_map[str(import_batch_id)]
                if import_batch_id is not None
                else None
            )
            self.execution_repo.insert_one(new_doc)
            summary["executions"]["created"] += 1

    def _restore_media(
        self,
        destination_user_id: str,
        media_docs: List[dict],
        trade_id_map: dict[str, ObjectId],
        media_bytes: dict[str, bytes],
        summary: dict,
    ) -> None:
        """Restore media objects and metadata for inserted trades only."""
        client = get_client()
        bucket = get_bucket()
        ensure_bucket_exists(client, bucket)

        for source_doc in media_docs:
            source_trade_id = source_doc.get("trade_id")
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
