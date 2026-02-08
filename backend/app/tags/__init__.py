"""Tags blueprint."""

from flask import Blueprint

tags_bp = Blueprint(
    "tags", __name__, url_prefix="/api/tags"
)

from app.tags import routes  # noqa: E402, F401
