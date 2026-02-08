"""Trade Accounts blueprint."""

from flask import Blueprint

accounts_bp = Blueprint(
    "accounts", __name__, url_prefix="/api/accounts"
)

from app.accounts import routes  # noqa: E402, F401
