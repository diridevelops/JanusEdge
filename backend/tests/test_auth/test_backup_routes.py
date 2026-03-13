"""Tests for portable auth backup export and restore routes."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch
import json
import zipfile

from bson import ObjectId, json_util
import pytest

from app import create_app
from app.market_data.symbol_mapper import (
    get_default_symbol_mappings,
)
from app.models.execution import create_execution_doc
from app.models.import_batch import create_import_batch_doc
from app.models.market_data import create_market_data_doc
from app.models.media import create_media_doc
from app.models.tag import create_tag_doc
from app.models.trade import create_trade_doc
from app.models.trade_account import create_trade_account_doc
from app.utils.trade_fingerprint import (
    build_trade_fingerprint,
)
from config import TestingConfig


class _ObjectResponse:
    """Small file-like wrapper for the in-memory MinIO stub."""

    def __init__(self, payload: bytes) -> None:
        self._buffer = BytesIO(payload)

    def read(self) -> bytes:
        """Return the entire object payload."""
        return self._buffer.read()

    def close(self) -> None:
        """Close the underlying buffer."""
        self._buffer.close()

    def release_conn(self) -> None:
        """Match the MinIO response API."""


class InMemoryMinio:
    """Very small MinIO-compatible object store for tests."""

    def __init__(self, *args, **kwargs) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], dict] = {}

    def bucket_exists(self, bucket: str) -> bool:
        """Return True when the bucket already exists."""
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        """Create the bucket."""
        self.buckets.add(bucket)

    def put_object(
        self,
        bucket: str,
        object_name: str,
        data,
        length: int,
        content_type: str | None = None,
    ) -> None:
        """Store an object payload in memory."""
        self.buckets.add(bucket)
        self.objects[(bucket, object_name)] = {
            "payload": data.read(length),
            "content_type": content_type,
        }

    def get_object(self, bucket: str, object_name: str):
        """Return a readable response for a stored object."""
        return _ObjectResponse(
            self.objects[(bucket, object_name)]["payload"]
        )

    def remove_object(self, bucket: str, object_name: str) -> None:
        """Delete a stored object."""
        self.objects.pop((bucket, object_name), None)

    def presigned_get_object(
        self,
        bucket: str,
        object_name: str,
        expires=None,
    ) -> str:
        """Return a predictable fake presigned URL."""
        return f"http://minio.test/{bucket}/{object_name}"


@pytest.fixture
def app():
    """Create a Flask app with an in-memory MinIO stub."""
    with patch("app.storage.Minio", new=InMemoryMinio):
        application = create_app(TestingConfig)
        yield application


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean all relevant collections before each test."""
    with app.app_context():
        from app.extensions import mongo

        for collection in [
            "users",
            "trade_accounts",
            "tags",
            "import_batches",
            "trades",
            "executions",
            "media",
            "market_data_cache",
        ]:
            mongo.db[collection].delete_many({})
    yield


def _auth(token: str) -> dict:
    """Return the authorization header for a token."""
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(
    client, username: str
) -> tuple[str, str]:
    """Register a user, then log in and return token and user id."""
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    assert response.status_code == 201
    user_id = response.get_json()["user"]["id"]

    login_response = client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": "TestPass123!",
        },
    )
    assert login_response.status_code == 200
    token = login_response.get_json()["token"]
    return token, user_id


def _build_custom_symbol_mappings() -> dict:
    """Build a deterministic custom mapping set for backup tests."""
    symbol_mappings = get_default_symbol_mappings()
    symbol_mappings["MES"] = {
        "yahoo_symbol": "MES-CUSTOM=F",
        "dollar_value_per_point": 9.5,
    }
    return symbol_mappings


def _seed_portable_backup_graph(app, user_id: str) -> dict:
    """Seed a realistic export graph for a source user."""
    from app.extensions import mongo
    from app.media.service import MediaService
    from app.storage import get_bucket, get_client
    from app.repositories.user_repo import UserRepository

    user_oid = ObjectId(user_id)
    symbol_mappings = _build_custom_symbol_mappings()
    with app.app_context():
        user_repo = UserRepository()
        user_repo.update_portable_settings(
            user_id,
            timezone="America/Chicago",
            display_timezone="UTC",
            starting_equity=25000.0,
            symbol_mappings=symbol_mappings,
        )

        account_one = create_trade_account_doc(
            user_id=user_oid,
            account_name="Sim-101",
            source_platform="ninjatrader",
            display_name="Sim 101",
        )
        account_one["_id"] = ObjectId()
        account_one["notes"] = "Primary simulated account"
        account_two = create_trade_account_doc(
            user_id=user_oid,
            account_name="Live-202",
            source_platform="manual",
            display_name="Live 202",
        )
        account_two["_id"] = ObjectId()
        mongo.db.trade_accounts.insert_many([
            account_one,
            account_two,
        ])

        tag_one = create_tag_doc(
            user_id=user_oid,
            name="Breakout",
            category="strategy",
            color="#22C55E",
        )
        tag_one["_id"] = ObjectId()
        tag_two = create_tag_doc(
            user_id=user_oid,
            name="Review",
            category="process",
            color="#F97316",
        )
        tag_two["_id"] = ObjectId()
        mongo.db.tags.insert_many([tag_one, tag_two])

        batch_one = create_import_batch_doc(
            user_id=user_oid,
            file_name="mes-session.csv",
            file_hash="hash-mes-session",
            file_size_bytes=1024,
            platform="ninjatrader",
            stats={
                "total_rows": 4,
                "imported_rows": 4,
                "skipped_rows": 0,
                "error_rows": 0,
                "trades_reconstructed": 1,
            },
        )
        batch_one["_id"] = ObjectId()
        batch_deleted = create_import_batch_doc(
            user_id=user_oid,
            file_name="deleted-trade.csv",
            file_hash="hash-deleted-trade",
            file_size_bytes=256,
            platform="ninjatrader",
        )
        batch_deleted["_id"] = ObjectId()
        mongo.db.import_batches.insert_many([
            batch_one,
            batch_deleted,
        ])

        trade_one = create_trade_doc(
            user_id=user_oid,
            trade_account_id=account_one["_id"],
            import_batch_id=batch_one["_id"],
            symbol="MES",
            raw_symbol="MES 06-26",
            side="Long",
            total_quantity=2,
            max_quantity=2,
            avg_entry_price=5000.25,
            avg_exit_price=5008.75,
            gross_pnl=85.0,
            fee=4.5,
            fee_source="csv",
            net_pnl=80.5,
            initial_risk=125.0,
            entry_time=datetime(
                2026, 1, 2, 14, 30, tzinfo=timezone.utc
            ),
            exit_time=datetime(
                2026, 1, 2, 14, 38, tzinfo=timezone.utc
            ),
            holding_time_seconds=480,
            execution_count=2,
            source="imported",
        )
        trade_one["_id"] = ObjectId()
        trade_one["tag_ids"] = [tag_one["_id"], tag_two["_id"]]
        trade_one["strategy"] = "ORB"
        trade_one["pre_trade_notes"] = "Waited for pullback"
        trade_one["post_trade_notes"] = "Managed partials well"

        trade_two = create_trade_doc(
            user_id=user_oid,
            trade_account_id=account_two["_id"],
            import_batch_id=None,
            symbol="MES",
            raw_symbol="MES 06-26",
            side="Short",
            total_quantity=1,
            max_quantity=1,
            avg_entry_price=5012.0,
            avg_exit_price=5006.25,
            gross_pnl=28.75,
            fee=1.25,
            fee_source="manual_edit",
            net_pnl=27.5,
            initial_risk=75.0,
            entry_time=datetime(
                2026, 1, 3, 15, 0, tzinfo=timezone.utc
            ),
            exit_time=datetime(
                2026, 1, 3, 15, 7, tzinfo=timezone.utc
            ),
            holding_time_seconds=420,
            execution_count=1,
            source="manual",
        )
        trade_two["_id"] = ObjectId()
        trade_two["tag_ids"] = [tag_two["_id"]]
        trade_two["strategy"] = "Fade"

        deleted_trade = create_trade_doc(
            user_id=user_oid,
            trade_account_id=account_one["_id"],
            import_batch_id=batch_deleted["_id"],
            symbol="NQ",
            raw_symbol="NQ 06-26",
            side="Long",
            total_quantity=1,
            max_quantity=1,
            avg_entry_price=21000.0,
            avg_exit_price=21020.0,
            gross_pnl=40.0,
            fee=2.0,
            fee_source="csv",
            net_pnl=38.0,
            initial_risk=100.0,
            entry_time=datetime(
                2026, 1, 4, 14, 0, tzinfo=timezone.utc
            ),
            exit_time=datetime(
                2026, 1, 4, 14, 5, tzinfo=timezone.utc
            ),
            holding_time_seconds=300,
            execution_count=1,
            source="imported",
            status="deleted",
        )
        deleted_trade["_id"] = ObjectId()
        mongo.db.trades.insert_many([
            trade_one,
            trade_two,
            deleted_trade,
        ])

        execution_one = create_execution_doc(
            user_id=user_oid,
            trade_account_id=account_one["_id"],
            import_batch_id=batch_one["_id"],
            symbol="MES",
            raw_symbol="MES 06-26",
            side="Buy",
            quantity=1,
            price=5000.0,
            timestamp=datetime(
                2026, 1, 2, 14, 30, tzinfo=timezone.utc
            ),
            platform_execution_id="exec-1",
            raw_data={"row": 1},
        )
        execution_one["_id"] = ObjectId()
        execution_one["trade_id"] = trade_one["_id"]
        execution_two = create_execution_doc(
            user_id=user_oid,
            trade_account_id=account_one["_id"],
            import_batch_id=batch_one["_id"],
            symbol="MES",
            raw_symbol="MES 06-26",
            side="Sell",
            quantity=1,
            price=5008.75,
            timestamp=datetime(
                2026, 1, 2, 14, 38, tzinfo=timezone.utc
            ),
            platform_execution_id="exec-2",
            raw_data={"row": 2},
        )
        execution_two["_id"] = ObjectId()
        execution_two["trade_id"] = trade_one["_id"]
        execution_three = create_execution_doc(
            user_id=user_oid,
            trade_account_id=account_two["_id"],
            import_batch_id=None,
            symbol="MES",
            raw_symbol="MES 06-26",
            side="Sell",
            quantity=1,
            price=5012.0,
            timestamp=datetime(
                2026, 1, 3, 15, 0, tzinfo=timezone.utc
            ),
            platform_execution_id="exec-3",
            raw_data={"row": 3},
        )
        execution_three["_id"] = ObjectId()
        execution_three["trade_id"] = trade_two["_id"]
        deleted_execution = create_execution_doc(
            user_id=user_oid,
            trade_account_id=account_one["_id"],
            import_batch_id=batch_deleted["_id"],
            symbol="NQ",
            raw_symbol="NQ 06-26",
            side="Buy",
            quantity=1,
            price=21000.0,
            timestamp=datetime(
                2026, 1, 4, 14, 0, tzinfo=timezone.utc
            ),
        )
        deleted_execution["_id"] = ObjectId()
        deleted_execution["trade_id"] = deleted_trade["_id"]
        mongo.db.executions.insert_many([
            execution_one,
            execution_two,
            execution_three,
            deleted_execution,
        ])

        media_service = MediaService()
        bucket = get_bucket()
        client = get_client()
        media_payloads = {
            "trade-one-chart.png": b"trade-one-chart-bytes",
            "trade-two-note.png": b"trade-two-note-bytes",
            "deleted-trade.png": b"deleted-trade-bytes",
        }

        media_one_key = media_service._object_key(
            user_id,
            str(trade_one["_id"]),
            "trade-one-chart.png",
        )
        client.put_object(
            bucket,
            media_one_key,
            BytesIO(media_payloads["trade-one-chart.png"]),
            length=len(media_payloads["trade-one-chart.png"]),
            content_type="image/png",
        )
        media_one = create_media_doc(
            user_id=user_oid,
            trade_id=trade_one["_id"],
            object_key=media_one_key,
            original_filename="trade-one-chart.png",
            content_type="image/png",
            size_bytes=len(media_payloads["trade-one-chart.png"]),
            media_type="image",
        )
        media_one["_id"] = ObjectId()

        media_two_key = media_service._object_key(
            user_id,
            str(trade_two["_id"]),
            "trade-two-note.png",
        )
        client.put_object(
            bucket,
            media_two_key,
            BytesIO(media_payloads["trade-two-note.png"]),
            length=len(media_payloads["trade-two-note.png"]),
            content_type="image/png",
        )
        media_two = create_media_doc(
            user_id=user_oid,
            trade_id=trade_two["_id"],
            object_key=media_two_key,
            original_filename="trade-two-note.png",
            content_type="image/png",
            size_bytes=len(media_payloads["trade-two-note.png"]),
            media_type="image",
        )
        media_two["_id"] = ObjectId()

        deleted_media_key = media_service._object_key(
            user_id,
            str(deleted_trade["_id"]),
            "deleted-trade.png",
        )
        client.put_object(
            bucket,
            deleted_media_key,
            BytesIO(media_payloads["deleted-trade.png"]),
            length=len(media_payloads["deleted-trade.png"]),
            content_type="image/png",
        )
        deleted_media = create_media_doc(
            user_id=user_oid,
            trade_id=deleted_trade["_id"],
            object_key=deleted_media_key,
            original_filename="deleted-trade.png",
            content_type="image/png",
            size_bytes=len(media_payloads["deleted-trade.png"]),
            media_type="image",
        )
        deleted_media["_id"] = ObjectId()
        mongo.db.media.insert_many([
            media_one,
            media_two,
            deleted_media,
        ])

        market_day_one_5m = create_market_data_doc(
            symbol="MES-CUSTOM=F",
            interval="5m",
            date=datetime(2026, 1, 2),
            ohlc=[
                {
                    "time": 1767364200,
                    "open": 5000.0,
                    "high": 5004.0,
                    "low": 4999.5,
                    "close": 5003.25,
                    "volume": 100,
                }
            ],
            bar_count=1,
        )
        market_day_one_5m["_id"] = ObjectId()
        market_day_one_1m = create_market_data_doc(
            symbol="MES-CUSTOM=F",
            interval="1m",
            date=datetime(2026, 1, 2),
            ohlc=[
                {
                    "time": 1767364200,
                    "open": 5000.0,
                    "high": 5001.0,
                    "low": 4999.5,
                    "close": 5000.75,
                    "volume": 50,
                }
            ],
            bar_count=1,
        )
        market_day_one_1m["_id"] = ObjectId()
        market_day_two_5m = create_market_data_doc(
            symbol="MES-CUSTOM=F",
            interval="5m",
            date=datetime(2026, 1, 3),
            ohlc=[
                {
                    "time": 1767452400,
                    "open": 5012.0,
                    "high": 5012.25,
                    "low": 5007.0,
                    "close": 5008.0,
                    "volume": 80,
                }
            ],
            bar_count=1,
        )
        market_day_two_5m["_id"] = ObjectId()
        unrelated_market = create_market_data_doc(
            symbol="NQ=F",
            interval="5m",
            date=datetime(2026, 1, 2),
            ohlc=[
                {
                    "time": 1767364200,
                    "open": 21000.0,
                    "high": 21010.0,
                    "low": 20990.0,
                    "close": 21005.0,
                    "volume": 70,
                }
            ],
            bar_count=1,
        )
        unrelated_market["_id"] = ObjectId()
        mongo.db.market_data_cache.insert_many([
            market_day_one_5m,
            market_day_one_1m,
            market_day_two_5m,
            unrelated_market,
        ])

        return {
            "trade_one": trade_one,
            "trade_two": trade_two,
            "deleted_trade": deleted_trade,
            "symbol_mappings": symbol_mappings,
            "account_one": account_one,
            "account_two": account_two,
            "tag_one": tag_one,
            "tag_two": tag_two,
            "batch_one": batch_one,
            "media_payloads": {
                str(media_one["_id"]): media_payloads[
                    "trade-one-chart.png"
                ],
                str(media_two["_id"]): media_payloads[
                    "trade-two-note.png"
                ],
            },
        }


def _export_archive_bytes(client, token: str) -> bytes:
    """Export the authenticated user's backup and return the ZIP bytes."""
    response = client.get(
        "/api/auth/export",
        headers=_auth(token),
    )
    assert response.status_code == 200
    return response.data


def _parse_archive(archive_bytes: bytes) -> tuple[dict, dict, set[str]]:
    """Parse a backup archive into manifest, payload, and names."""
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        manifest = json.loads(
            archive.read("manifest.json").decode("utf-8")
        )
        payload = json_util.loads(
            archive.read("data.json").decode("utf-8")
        )
        return manifest, payload, set(archive.namelist())


def _rewrite_archive_payload(
    archive_bytes: bytes, payload: dict
) -> bytes:
    """Rewrite the backup payload while preserving archive media."""
    buffer = BytesIO()
    with zipfile.ZipFile(BytesIO(archive_bytes)) as source_archive:
        manifest = json.loads(
            source_archive.read("manifest.json").decode("utf-8")
        )
        media_entries = {
            name: source_archive.read(name)
            for name in source_archive.namelist()
            if name.startswith("media/")
        }

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2).encode("utf-8"),
        )
        archive.writestr(
            "data.json",
            json_util.dumps(payload, indent=2).encode("utf-8"),
        )
        for name, media_bytes in media_entries.items():
            archive.writestr(name, media_bytes)

    return buffer.getvalue()


def _restore_archive(client, token: str, archive_bytes: bytes):
    """POST a backup archive to the restore route."""
    return client.post(
        "/api/auth/restore",
        headers=_auth(token),
        data={
            "file": (
                BytesIO(archive_bytes),
                "portable-backup.zip",
            )
        },
        content_type="multipart/form-data",
    )


def test_export_backup_is_complete_and_self_contained(
    client, app
):
    """Export includes all active graph data and media binaries."""
    token, user_id = _register_and_login(client, "source-export")
    seeded = _seed_portable_backup_graph(app, user_id)

    archive_bytes = _export_archive_bytes(client, token)
    manifest, payload, names = _parse_archive(archive_bytes)

    assert manifest["archive_type"] == "janusedge-portable-backup"
    assert manifest["version"] == "1.0"
    assert manifest["counts"] == {
        "accounts": 2,
        "tags": 2,
        "import_batches": 1,
        "trades": 2,
        "executions": 3,
        "media": 2,
        "market_data_cache": 3,
    }
    assert payload["settings"] == {
        "timezone": "America/Chicago",
        "display_timezone": "UTC",
        "starting_equity": 25000.0,
        "symbol_mappings": seeded["symbol_mappings"],
    }

    exported_trade_ids = {str(trade["_id"]) for trade in payload["trades"]}
    assert str(seeded["trade_one"]["_id"]) in exported_trade_ids
    assert str(seeded["trade_two"]["_id"]) in exported_trade_ids
    assert str(seeded["deleted_trade"]["_id"]) not in exported_trade_ids
    assert all(trade["status"] != "deleted" for trade in payload["trades"])
    assert all(
        batch["file_hash"] != "hash-deleted-trade"
        for batch in payload["import_batches"]
    )
    assert {cache["interval"] for cache in payload["market_data_cache"]} == {
        "1m",
        "5m",
    }
    assert {cache["symbol"] for cache in payload["market_data_cache"]} == {
        "MES-CUSTOM=F"
    }

    media_entries = payload["media"]
    assert len(media_entries) == 2
    for media_doc in media_entries:
        assert media_doc["archive_path"] in names
        assert media_doc["archive_path"].startswith("media/")

    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        for media_doc in media_entries:
            media_bytes = archive.read(media_doc["archive_path"])
            assert (
                media_bytes
                == seeded["media_payloads"][str(media_doc["_id"])]
            )


def test_restore_into_different_user_remaps_graph_and_media(
    client, app
):
    """Restore remaps all foreign keys into the destination user."""
    source_token, source_user_id = _register_and_login(
        client, "source-restore"
    )
    seeded = _seed_portable_backup_graph(app, source_user_id)
    archive_bytes = _export_archive_bytes(client, source_token)

    dest_token, dest_user_id = _register_and_login(
        client, "destination-restore"
    )
    response = _restore_archive(client, dest_token, archive_bytes)
    assert response.status_code == 200

    summary = response.get_json()["summary"]
    assert summary["accounts"] == {"created": 2, "reused": 0}
    assert summary["tags"] == {"created": 2, "reused": 0}
    assert summary["import_batches"] == {
        "created": 1,
        "reused": 0,
    }
    assert summary["trades"] == {"created": 2, "skipped": 0}
    assert summary["executions"] == {
        "created": 3,
        "skipped": 0,
    }
    assert summary["media"] == {"created": 2, "skipped": 0}
    assert summary["market_data_cache"] == {"upserted": 3}

    with app.app_context():
        from app.extensions import mongo
        from app.storage import get_bucket, get_client

        restored_user = mongo.db.users.find_one(
            {"_id": ObjectId(dest_user_id)}
        )
        assert restored_user["username"] == "destination-restore"
        assert restored_user["timezone"] == "America/Chicago"
        assert restored_user["display_timezone"] == "UTC"
        assert restored_user["starting_equity"] == 25000.0
        assert (
            restored_user["symbol_mappings"]
            == seeded["symbol_mappings"]
        )
        assert "password_hash" in restored_user

        restored_accounts = list(
            mongo.db.trade_accounts.find(
                {"user_id": ObjectId(dest_user_id)}
            )
        )
        restored_tags = list(
            mongo.db.tags.find({"user_id": ObjectId(dest_user_id)})
        )
        restored_batches = list(
            mongo.db.import_batches.find(
                {"user_id": ObjectId(dest_user_id)}
            )
        )
        restored_trades = list(
            mongo.db.trades.find(
                {
                    "user_id": ObjectId(dest_user_id),
                    "status": {"$ne": "deleted"},
                }
            )
        )
        restored_executions = list(
            mongo.db.executions.find(
                {"user_id": ObjectId(dest_user_id)}
            )
        )
        restored_media = list(
            mongo.db.media.find({"user_id": ObjectId(dest_user_id)})
        )

        assert len(restored_accounts) == 2
        assert len(restored_tags) == 2
        assert len(restored_batches) == 1
        assert len(restored_trades) == 2
        assert len(restored_executions) == 3
        assert len(restored_media) == 2
        assert {
            trade["_id"] for trade in restored_trades
        }.isdisjoint(
            {seeded["trade_one"]["_id"], seeded["trade_two"]["_id"]}
        )
        restored_trade_ids = {trade["_id"] for trade in restored_trades}
        restored_account_ids = {acct["_id"] for acct in restored_accounts}
        restored_batch_ids = {batch["_id"] for batch in restored_batches}
        restored_tag_ids = {tag["_id"] for tag in restored_tags}

        for trade in restored_trades:
            assert trade["trade_account_id"] in restored_account_ids
            if trade.get("import_batch_id") is not None:
                assert trade["import_batch_id"] in restored_batch_ids
            assert set(trade.get("tag_ids", [])).issubset(
                restored_tag_ids
            )

        for execution in restored_executions:
            assert execution["trade_id"] in restored_trade_ids
            assert execution["trade_account_id"] in restored_account_ids
            if execution.get("import_batch_id") is not None:
                assert (
                    execution["import_batch_id"]
                    in restored_batch_ids
                )

        client_store = get_client()
        bucket = get_bucket()
        for media_doc in restored_media:
            assert media_doc["trade_id"] in restored_trade_ids
            assert media_doc["object_key"].startswith(
                f"{dest_user_id}/"
            )
            stored = client_store.get_object(
                bucket, media_doc["object_key"]
            ).read()
            assert stored in seeded["media_payloads"].values()

        restored_cache = list(
            mongo.db.market_data_cache.find(
                {"symbol": "MES-CUSTOM=F"}
            )
        )
        assert len(restored_cache) == 3


def test_restore_merge_into_empty_user_creates_all_records(
    client, app
):
    """Restore into an empty user creates the full graph."""
    source_token, source_user_id = _register_and_login(
        client, "source-empty-merge"
    )
    _seed_portable_backup_graph(app, source_user_id)
    archive_bytes = _export_archive_bytes(client, source_token)

    dest_token, _ = _register_and_login(
        client, "empty-merge-destination"
    )
    response = _restore_archive(client, dest_token, archive_bytes)
    assert response.status_code == 200
    assert response.get_json()["summary"] == {
        "accounts": {"created": 2, "reused": 0},
        "tags": {"created": 2, "reused": 0},
        "import_batches": {"created": 1, "reused": 0},
        "trades": {"created": 2, "skipped": 0},
        "executions": {"created": 3, "skipped": 0},
        "media": {"created": 2, "skipped": 0},
        "market_data_cache": {"upserted": 3},
        "settings": {
            "updated": [
                "timezone",
                "display_timezone",
                "starting_equity",
                "symbol_mappings",
            ]
        },
    }


def test_restore_merge_skips_duplicates_and_reuses_natural_keys(
    client, app
):
    """Restore reuses accounts, tags, batches, and skips duplicate trades."""
    source_token, source_user_id = _register_and_login(
        client, "source-partial-merge"
    )
    seeded = _seed_portable_backup_graph(app, source_user_id)
    archive_bytes = _export_archive_bytes(client, source_token)

    dest_token, dest_user_id = _register_and_login(
        client, "partial-merge-destination"
    )

    with app.app_context():
        from app.extensions import mongo

        dest_oid = ObjectId(dest_user_id)
        existing_account = create_trade_account_doc(
            user_id=dest_oid,
            account_name="Sim-101",
            source_platform="manual",
            display_name="Existing Sim",
        )
        existing_account["_id"] = ObjectId()
        existing_tag = create_tag_doc(
            user_id=dest_oid,
            name="Breakout",
            category="strategy",
            color="#000000",
        )
        existing_tag["_id"] = ObjectId()
        existing_batch = create_import_batch_doc(
            user_id=dest_oid,
            file_name="existing.csv",
            file_hash="hash-mes-session",
            file_size_bytes=1,
            platform="ninjatrader",
        )
        existing_batch["_id"] = ObjectId()
        duplicate_trade = create_trade_doc(
            user_id=dest_oid,
            trade_account_id=existing_account["_id"],
            import_batch_id=existing_batch["_id"],
            symbol=seeded["trade_one"]["symbol"],
            raw_symbol=seeded["trade_one"]["raw_symbol"],
            side=seeded["trade_one"]["side"],
            total_quantity=seeded["trade_one"]["total_quantity"],
            max_quantity=seeded["trade_one"]["max_quantity"],
            avg_entry_price=seeded["trade_one"]["avg_entry_price"],
            avg_exit_price=seeded["trade_one"]["avg_exit_price"],
            gross_pnl=999.0,
            fee=0.0,
            fee_source="manual_edit",
            net_pnl=999.0,
            initial_risk=10.0,
            entry_time=seeded["trade_one"]["entry_time"],
            exit_time=seeded["trade_one"]["exit_time"],
            holding_time_seconds=60,
            execution_count=1,
            source=seeded["trade_one"]["source"],
        )
        duplicate_trade["_id"] = ObjectId()
        duplicate_trade["tag_ids"] = [existing_tag["_id"]]
        mongo.db.trade_accounts.insert_one(existing_account)
        mongo.db.tags.insert_one(existing_tag)
        mongo.db.import_batches.insert_one(existing_batch)
        mongo.db.trades.insert_one(duplicate_trade)

    response = _restore_archive(client, dest_token, archive_bytes)
    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["accounts"] == {"created": 1, "reused": 1}
    assert summary["tags"] == {"created": 1, "reused": 1}
    assert summary["import_batches"] == {
        "created": 0,
        "reused": 1,
    }
    assert summary["trades"] == {"created": 1, "skipped": 1}
    assert summary["executions"] == {
        "created": 1,
        "skipped": 2,
    }
    assert summary["media"] == {"created": 1, "skipped": 1}


def test_restore_duplicate_detection_uses_stable_trade_fingerprint_only(
    client, app
):
    """Duplicate trade matching ignores non-fingerprint fields."""
    source_token, source_user_id = _register_and_login(
        client, "source-fingerprint"
    )
    seeded = _seed_portable_backup_graph(app, source_user_id)
    archive_bytes = _export_archive_bytes(client, source_token)

    dest_token, dest_user_id = _register_and_login(
        client, "dest-fingerprint"
    )

    with app.app_context():
        from app.extensions import mongo

        dest_oid = ObjectId(dest_user_id)
        account = create_trade_account_doc(
            user_id=dest_oid,
            account_name="Different-Account",
            source_platform="manual",
            display_name="Different Account",
        )
        account["_id"] = ObjectId()
        batch = create_import_batch_doc(
            user_id=dest_oid,
            file_name="different.csv",
            file_hash="dest-different-hash",
            file_size_bytes=12,
            platform="manual",
        )
        batch["_id"] = ObjectId()
        tag = create_tag_doc(
            user_id=dest_oid,
            name="DifferentTag",
            category="custom",
            color="#123456",
        )
        tag["_id"] = ObjectId()
        trade = create_trade_doc(
            user_id=dest_oid,
            trade_account_id=account["_id"],
            import_batch_id=batch["_id"],
            symbol=seeded["trade_one"]["symbol"],
            raw_symbol="totally-different-raw-symbol",
            side=seeded["trade_one"]["side"],
            total_quantity=seeded["trade_one"]["total_quantity"],
            max_quantity=99,
            avg_entry_price=seeded["trade_one"]["avg_entry_price"],
            avg_exit_price=seeded["trade_one"]["avg_exit_price"],
            gross_pnl=-1.0,
            fee=0.0,
            fee_source="manual_edit",
            net_pnl=-1.0,
            initial_risk=999.0,
            entry_time=seeded["trade_one"]["entry_time"],
            exit_time=seeded["trade_one"]["exit_time"],
            holding_time_seconds=5,
            execution_count=99,
            source=seeded["trade_one"]["source"],
        )
        trade["_id"] = ObjectId()
        trade["tag_ids"] = [tag["_id"]]
        trade["strategy"] = "Different Strategy"
        mongo.db.trade_accounts.insert_one(account)
        mongo.db.import_batches.insert_one(batch)
        mongo.db.tags.insert_one(tag)
        mongo.db.trades.insert_one(trade)

        existing_fingerprint = build_trade_fingerprint(trade)
        source_fingerprint = build_trade_fingerprint(
            seeded["trade_one"]
        )
        assert existing_fingerprint == source_fingerprint

    response = _restore_archive(client, dest_token, archive_bytes)
    assert response.status_code == 200
    assert response.get_json()["summary"]["trades"] == {
        "created": 1,
        "skipped": 1,
    }


@pytest.mark.parametrize(
    ("payload_builder", "expected_message"),
    [
        (
            lambda: b"not-a-zip-file",
            "Invalid backup archive.",
        ),
        (
            lambda: _build_missing_manifest_archive(),
            "Backup archive is missing required files.",
        ),
    ],
)
def test_restore_rejects_invalid_archives(
    client, payload_builder, expected_message
):
    """Restore returns 400 for invalid or incomplete archives."""
    token, _ = _register_and_login(client, "invalid-archive-user")
    response = _restore_archive(
        client,
        token,
        payload_builder(),
    )
    assert response.status_code == 400
    assert (
        response.get_json()["error"]["message"]
        == expected_message
    )


def test_restore_rejects_invalid_symbol_mappings(
    client, app
):
    """Restore rejects archives with invalid symbol mappings."""
    token, user_id = _register_and_login(
        client, "invalid-symbol-mappings"
    )
    _seed_portable_backup_graph(app, user_id)
    archive_bytes = _export_archive_bytes(client, token)
    _, payload, _ = _parse_archive(archive_bytes)
    payload["settings"]["symbol_mappings"]["MES"][
        "dollar_value_per_point"
    ] = 0

    response = _restore_archive(
        client,
        token,
        _rewrite_archive_payload(archive_bytes, payload),
    )

    assert response.status_code == 400
    assert (
        response.get_json()["error"]["message"]
        == "Backup archive contains invalid symbol mappings."
    )


def _build_missing_manifest_archive() -> bytes:
    """Build an archive missing its manifest for validation tests."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.json", json.dumps({}))
    return buffer.getvalue()