"""Public client-config blueprint."""

from flask import Blueprint

client_config_bp = Blueprint(
    "client_config", __name__, url_prefix="/api"
)

from app.client_config import routes  # noqa: E402, F401
