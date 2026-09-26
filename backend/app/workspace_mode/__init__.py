"""Workspace-mode API blueprint."""

from flask import Blueprint

workspace_mode_bp = Blueprint(
    "workspace_mode", __name__, url_prefix="/api/workspace"
)

from app.workspace_mode import routes  # noqa: E402, F401
