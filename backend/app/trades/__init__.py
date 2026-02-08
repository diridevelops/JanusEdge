"""Trades blueprint."""

from flask import Blueprint

trades_bp = Blueprint(
    "trades", __name__, url_prefix="/api/trades"
)

from app.trades import routes  # noqa: E402, F401
