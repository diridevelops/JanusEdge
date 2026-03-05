"""What-if blueprint for stop analysis and simulation."""

from flask import Blueprint

whatif_bp = Blueprint(
    "whatif", __name__, url_prefix="/api/whatif"
)

from app.whatif import routes  # noqa: E402, F401
