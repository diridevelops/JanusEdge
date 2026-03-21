"""Pytest fixtures for Janus Edge tests."""

from datetime import date
from io import BytesIO
from unittest.mock import MagicMock

import pandas as pd
import pytest

import app.storage as storage_module
from app import create_app
from app.models.market_data import create_market_data_doc
from app.repositories.market_data_repo import MarketDataRepository
from app.tick_data.parquet_store import MarketDataParquetStore
from config import TestingConfig


class _ObjectResponse:
    """Small file-like wrapper for the in-memory MinIO stub."""

    def __init__(self, payload: bytes) -> None:
        self._buffer = BytesIO(payload)

    def read(self) -> bytes:
        """Return the stored object payload."""

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
        self.bucket_exists = MagicMock(
            side_effect=self._bucket_exists
        )
        self.make_bucket = MagicMock(
            side_effect=self._make_bucket
        )
        self.put_object = MagicMock(
            side_effect=self._put_object
        )
        self.get_object = MagicMock(
            side_effect=self._get_object
        )
        self.remove_object = MagicMock(
            side_effect=self._remove_object
        )
        self.presigned_get_object = MagicMock(
            side_effect=self._presigned_get_object
        )

    def _bucket_exists(self, bucket: str) -> bool:
        """Return True when the bucket exists."""

        return bucket in self.buckets

    def _make_bucket(self, bucket: str) -> None:
        """Create a new bucket."""

        self.buckets.add(bucket)

    def _put_object(
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

    def _get_object(self, bucket: str, object_name: str):
        """Return a readable response for a stored object."""

        return _ObjectResponse(
            self.objects[(bucket, object_name)]["payload"]
        )

    def _remove_object(
        self, bucket: str, object_name: str
    ) -> None:
        """Delete a stored object."""

        self.objects.pop((bucket, object_name), None)

    def _presigned_get_object(
        self,
        bucket: str,
        object_name: str,
        expires=None,
    ) -> str:
        """Return a predictable fake presigned URL."""

        return f"http://minio.test/{bucket}/{object_name}"


storage_module.Minio = InMemoryMinio


@pytest.fixture(autouse=True)
def patch_minio(monkeypatch):
    """Replace the MinIO client with an in-memory test stub."""

    monkeypatch.setattr("app.storage.Minio", InMemoryMinio)
    storage_module._client = None
    storage_module._media_bucket = ""
    storage_module._market_data_bucket = ""
    yield
    storage_module._client = None
    storage_module._media_bucket = ""
    storage_module._market_data_bucket = ""


@pytest.fixture
def app(patch_minio):
    """Create a test Flask application."""
    application = create_app(TestingConfig)
    yield application


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture
def seed_market_data_dataset(app):
    """Persist a candle or tick dataset and its metadata for tests."""

    def _seed(
        *,
        symbol: str,
        trading_day: date,
        dataset_type: str,
        rows: list[dict],
        timeframe: str | None = None,
        raw_symbol: str | None = None,
        source_file_name: str = "test-source.txt",
        import_batch_id: str | None = None,
    ) -> dict:
        with app.app_context():
            frame = pd.DataFrame(rows)
            object_key_parts = [symbol, dataset_type]
            if timeframe is not None:
                object_key_parts.append(timeframe)
            object_key_parts.extend(
                [
                    f"{trading_day.year:04d}",
                    f"{trading_day.month:02d}",
                    f"{trading_day.day:02d}.parquet",
                ]
            )
            object_key = "/".join(object_key_parts)

            byte_size = MarketDataParquetStore().write_dataframe(
                object_key,
                frame,
            )
            document = create_market_data_doc(
                symbol=symbol,
                raw_symbol=raw_symbol,
                dataset_type=dataset_type,
                timeframe=timeframe,
                date=trading_day,
                object_key=object_key,
                row_count=len(frame.index),
                byte_size=byte_size,
                source_file_name=source_file_name,
                import_batch_id=import_batch_id,
            )
            MarketDataRepository().upsert_document(document)
            return document

    return _seed
