"""Executions blueprint."""

from flask import Blueprint

executions_bp = Blueprint(
    "executions", __name__, url_prefix="/api/executions"
)

from app.executions import routes  # noqa: E402, F401
