"""Configuration classes for Janus Edge."""

import os
from datetime import timedelta
from typing import Mapping

from dotenv import load_dotenv

load_dotenv()

REQUIRED_CONFIG_VARS = (
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
)


def _get_env(name: str, default: str | None = None) -> str | None:
    """Return a trimmed environment variable or the provided default."""
    value = os.environ.get(name)
    if value is None:
        return default

    value = value.strip()
    return value or default


def validate_config(config: Mapping[str, object]) -> None:
    """Ensure required secret values are set before booting the app."""
    missing = [
        name
        for name in REQUIRED_CONFIG_VARS
        if not isinstance(config.get(name), str)
        or not str(config.get(name)).strip()
    ]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            "Missing required environment variables: "
            f"{joined}. Copy backend/.env.example for local "
            "backend development or .env.example for Docker Compose."
        )


class Config:
    """Base configuration."""

    SECRET_KEY = _get_env("SECRET_KEY")
    MONGO_URI = _get_env(
        "MONGO_URI", "mongodb://localhost:27017/janusedge"
    )
    JWT_SECRET_KEY = _get_env("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_TYPE = "Bearer"
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500 MB upload
    CORS_ORIGINS = _get_env(
        "CORS_ORIGINS", "http://localhost:5173"
    )

    # MinIO object storage
    MINIO_ENDPOINT = _get_env(
        "MINIO_ENDPOINT", "localhost:9000"
    )
    MINIO_ACCESS_KEY = _get_env("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY = _get_env("MINIO_SECRET_KEY")
    MINIO_BUCKET = _get_env(
        "MINIO_BUCKET", "janusedge-media"
    )
    MINIO_USE_SSL = (
        _get_env("MINIO_USE_SSL", "false").lower()
        == "true"
    )
    # Public URL for presigned links (defaults to
    # localhost for local dev)
    MINIO_PUBLIC_URL = _get_env(
        "MINIO_PUBLIC_URL", "http://localhost:9000"
    )


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    SECRET_KEY = _get_env("SECRET_KEY", "test-secret-key")
    JWT_SECRET_KEY = _get_env(
        "JWT_SECRET_KEY", "test-jwt-secret-key"
    )
    MONGO_URI = os.environ.get(
        "MONGO_URI_TEST",
        "mongodb://localhost:27017/janusedge_test",
    )
    MINIO_ACCESS_KEY = _get_env(
        "MINIO_ACCESS_KEY", "test-minio-access-key"
    )
    MINIO_SECRET_KEY = _get_env(
        "MINIO_SECRET_KEY", "test-minio-secret-key"
    )


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
