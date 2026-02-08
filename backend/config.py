"""Configuration classes for TradeLogs application."""

import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
    MONGO_URI = os.environ.get(
        "MONGO_URI", "mongodb://localhost:27017/tradelogs"
    )
    JWT_SECRET_KEY = os.environ.get(
        "JWT_SECRET_KEY", "jwt-dev-secret"
    )
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_TYPE = "Bearer"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB upload limit
    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173"
    )


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    MONGO_URI = os.environ.get(
        "MONGO_URI_TEST",
        "mongodb://localhost:27017/tradelogs_test",
    )


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
