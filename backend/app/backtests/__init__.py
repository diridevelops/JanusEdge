"""Backtest workspace API blueprint."""

from flask import Blueprint

backtest_bp = Blueprint(
    "backtests", __name__, url_prefix="/api/backtest"
)

# Import route decorators after the blueprint exists so the application
# factory can register one complete feature blueprint.
from app.backtests import routes as _routes  # noqa: E402,F401
