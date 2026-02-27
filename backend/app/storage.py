"""MinIO object storage client for TradeLogs."""

import logging

from flask import Flask
from minio import Minio

logger = logging.getLogger(__name__)

# Module-level singleton
_client: Minio | None = None
_bucket: str = ""


def init_storage(app: Flask) -> None:
    """
    Initialise the MinIO client and ensure the
    media bucket exists.

    Parameters:
        app: The Flask application instance.
    """
    global _client, _bucket

    endpoint = app.config["MINIO_ENDPOINT"]
    access_key = app.config["MINIO_ACCESS_KEY"]
    secret_key = app.config["MINIO_SECRET_KEY"]
    use_ssl = app.config.get("MINIO_USE_SSL", False)
    _bucket = app.config["MINIO_BUCKET"]

    _client = Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=use_ssl,
    )

    # Create the bucket if it does not exist
    if not _client.bucket_exists(_bucket):
        _client.make_bucket(_bucket)
        logger.info("Created MinIO bucket: %s", _bucket)
    else:
        logger.info(
            "MinIO bucket already exists: %s", _bucket
        )


def get_client() -> Minio:
    """
    Return the initialised MinIO client.

    Raises:
        RuntimeError: If called before init_storage.
    """
    if _client is None:
        raise RuntimeError(
            "MinIO client not initialised. "
            "Call init_storage(app) first."
        )
    return _client


def get_bucket() -> str:
    """
    Return the configured media bucket name.

    Raises:
        RuntimeError: If called before init_storage.
    """
    if not _bucket:
        raise RuntimeError(
            "MinIO bucket not configured. "
            "Call init_storage(app) first."
        )
    return _bucket
