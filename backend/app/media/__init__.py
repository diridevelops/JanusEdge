"""Media attachments blueprint."""

from flask import Blueprint

media_bp = Blueprint(
    "media", __name__, url_prefix="/api"
)

from app.media import routes  # noqa: E402, F401
