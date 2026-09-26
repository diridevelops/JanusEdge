"""Authenticated read and update routes for workspace mode."""

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.workspace_mode import workspace_mode_bp
from app.workspace_mode.service import WorkspaceModeService
from app.utils.errors import ValidationError


workspace_mode_service = WorkspaceModeService()


@workspace_mode_bp.route("/mode", methods=["GET"])
@jwt_required()
def get_mode():
    """Return the current user's active workspace mode."""
    active_mode = workspace_mode_service.get_active_mode(
        get_jwt_identity()
    )
    return jsonify({"active_mode": active_mode}), 200


@workspace_mode_bp.route("/mode", methods=["PUT"])
@jwt_required()
def update_mode():
    """Persist a validated workspace mode for the JWT owner."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("Request body is required.")
    active_mode = workspace_mode_service.set_active_mode(
        get_jwt_identity(), body.get("active_mode")
    )
    return jsonify({"active_mode": active_mode}), 200
