"""Authentication API routes."""

from flask import jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)
from marshmallow import ValidationError as MarshmallowError

from app.auth import auth_bp
from app.auth.schemas import (
    LoginSchema,
    RegisterSchema,
    ChangePasswordSchema,
    UpdateTimezoneSchema,
)
from app.auth.service import AuthService
from app.utils.errors import ValidationError

auth_service = AuthService()
register_schema = RegisterSchema()
login_schema = LoginSchema()
change_password_schema = ChangePasswordSchema()
update_timezone_schema = UpdateTimezoneSchema()


@auth_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint for auth blueprint."""
    return {"status": "ok"}


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Register a new user account.

    Expects JSON: {username, password, timezone}
    Returns: {token, user}
    """
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = register_schema.load(data)
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    result = auth_service.register(
        username=validated["username"],
        password=validated["password"],
        timezone=validated["timezone"],
    )
    return jsonify(result), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate user and return JWT token.

    Expects JSON: {username, password}
    Returns: {token, user}
    """
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = login_schema.load(data)
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    result = auth_service.login(
        username=validated["username"],
        password=validated["password"],
    )
    return jsonify(result), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """
    Get current user profile.

    Requires: JWT Authorization header.
    Returns: {user}
    """
    user_id = get_jwt_identity()
    profile = auth_service.get_profile(user_id)
    return jsonify(profile), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """
    Logout (client-side token discard).

    Returns: {message}
    """
    return jsonify({"message": "Logged out."}), 200


@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    """
    Change the current user's password.

    Expects JSON: {current_password, new_password}
    Returns: {message}
    """
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = change_password_schema.load(data)
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    user_id = get_jwt_identity()
    result = auth_service.change_password(
        user_id=user_id,
        current_password=validated["current_password"],
        new_password=validated["new_password"],
    )
    return jsonify(result), 200


@auth_bp.route("/timezone", methods=["PUT"])
@jwt_required()
def update_timezone():
    """
    Update the current user's trading timezone.

    Expects JSON: {timezone}
    Returns: {user}
    """
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = update_timezone_schema.load(data)
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    user_id = get_jwt_identity()
    profile = auth_service.update_timezone(
        user_id=user_id,
        timezone=validated["timezone"],
    )
    return jsonify(profile), 200
