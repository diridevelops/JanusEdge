"""Market Data blueprint."""

from flask import Blueprint

market_data_bp = Blueprint(
    "market_data", __name__,
    url_prefix="/api/market-data",
)

from app.market_data import routes  # noqa: E402, F401
