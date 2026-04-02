"""MinIO object storage client for Janus Edge."""

import logging
from urllib.parse import urlsplit

from flask import Flask
from minio import Minio

logger = logging.getLogger(__name__)

MINIO_DEFAULT_REGION = "us-east-1"

# Module-level singleton
_client: Minio | None = None
_public_client: Minio | None = None
_media_bucket: str = ""
_market_data_bucket: str = ""


def _ensure_bucket(client: Minio, bucket: str) -> None:
    """Create a bucket when it does not already exist."""

    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)
        return

    logger.info("MinIO bucket already exists: %s", bucket)


def _build_public_client(
    public_url: str,
    *,
    access_key: str,
    secret_key: str,
    fallback: Minio,
) -> Minio:
    """
    Build the MinIO client used for browser-facing
    presigned URLs.

    Falls back to the internal client when the public
    URL is missing or invalid.
    """

    if not isinstance(public_url, str):
        return fallback

    parsed = urlsplit(public_url.strip())
    if not parsed.scheme or not parsed.netloc:
        logger.warning(
            "MINIO_PUBLIC_URL is invalid; falling back to "
            "MINIO_ENDPOINT for presigned URLs."
        )
        return fallback

    return Minio(
        parsed.netloc,
        access_key=access_key,
        secret_key=secret_key,
        secure=parsed.scheme == "https",
        region=MINIO_DEFAULT_REGION,
    )


def init_storage(app: Flask) -> None:
    """
    Initialise the MinIO client and ensure the
    media bucket exists.

    Parameters:
        app: The Flask application instance.
    """

    global _client, _public_client
    global _media_bucket, _market_data_bucket

    endpoint = app.config["MINIO_ENDPOINT"]
    access_key = app.config["MINIO_ACCESS_KEY"]
    secret_key = app.config["MINIO_SECRET_KEY"]
    use_ssl = app.config.get("MINIO_USE_SSL", False)
    _media_bucket = app.config["MINIO_BUCKET"]
    _market_data_bucket = app.config[
        "MINIO_MARKET_DATA_BUCKET"
    ]

    _client = Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=use_ssl,
    )
    _public_client = _build_public_client(
        app.config.get("MINIO_PUBLIC_URL", ""),
        access_key=access_key,
        secret_key=secret_key,
        fallback=_client,
    )

    _ensure_bucket(_client, _media_bucket)
    _ensure_bucket(_client, _market_data_bucket)


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


def get_public_client() -> Minio:
    """
    Return the client used for browser-facing
    presigned URLs.

    Raises:
        RuntimeError: If called before init_storage.
    """

    if _public_client is None:
        raise RuntimeError(
            "Public MinIO client not initialised. "
            "Call init_storage(app) first."
        )
    return _public_client


def get_bucket() -> str:
    """
    Return the configured media bucket name.

    Raises:
        RuntimeError: If called before init_storage.
    """

    if not _media_bucket:
        raise RuntimeError(
            "MinIO bucket not configured. "
            "Call init_storage(app) first."
        )
    return _media_bucket


def get_market_data_bucket() -> str:
    """Return the configured market-data bucket name."""

    if not _market_data_bucket:
        raise RuntimeError(
            "Market-data bucket not configured. "
            "Call init_storage(app) first."
        )
    return _market_data_bucket
