"""CSV Import blueprint."""

from flask import Blueprint

imports_bp = Blueprint(
    "imports", __name__, url_prefix="/api/imports"
)

from app.imports import routes  # noqa: E402, F401
