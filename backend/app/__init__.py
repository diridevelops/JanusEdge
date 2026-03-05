"""Flask application factory for TradeLogs."""

import logging

from flask import Flask

from config import DevelopmentConfig


def create_app(config_class=None):
    """
    Create and configure the Flask application.

    Parameters:
        config_class: Configuration class to use. Defaults
            to DevelopmentConfig.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)

    if config_class is None:
        config_class = DevelopmentConfig
    app.config.from_object(config_class)

    # Configure logging
    if app.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(name)s: "
            "%(message)s",
        )
        app.logger.setLevel(logging.DEBUG)
        # Silence noisy third-party loggers
        logging.getLogger("pymongo").setLevel(
            logging.WARNING
        )
        logging.getLogger("urllib3").setLevel(
            logging.WARNING
        )
        logging.getLogger("yfinance").setLevel(
            logging.WARNING
        )

    # Initialize extensions
    from app.extensions import mongo, jwt, cors

    mongo.init_app(app)
    jwt.init_app(app)
    cors.init_app(
        app,
        origins=app.config.get(
            "CORS_ORIGINS", "http://localhost:5173"
        ).split(","),
        supports_credentials=True,
    )

    # Register error handlers
    from app.middleware.error_handler import (
        register_error_handlers,
    )

    register_error_handlers(app)

    # Register blueprints
    from app.auth import auth_bp
    from app.imports import imports_bp
    from app.trades import trades_bp
    from app.executions import executions_bp
    from app.accounts import accounts_bp
    from app.tags import tags_bp
    from app.market_data import market_data_bp
    from app.analytics import analytics_bp
    from app.media import media_bp
    from app.whatif import whatif_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(trades_bp)
    app.register_blueprint(executions_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(market_data_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(whatif_bp)

    # Initialise MinIO object storage
    try:
        from app.storage import init_storage

        init_storage(app)
    except Exception:
        app.logger.warning(
            "MinIO unavailable — media uploads disabled"
        )

    # Initialize database indexes on first request
    with app.app_context():
        try:
            from app.db import init_db

            init_db(mongo.db)
        except Exception:
            # DB may not be available during testing
            pass

    return app
