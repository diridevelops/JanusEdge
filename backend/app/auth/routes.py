"""Authentication API routes."""

from flask import (
    current_app,
    jsonify,
    make_response,
    request,
    send_file,
)
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
)
from marshmallow import ValidationError as MarshmallowError

from app.auth import auth_bp
from app.auth.schemas import (
    LoginSchema,
    RegisterSchema,
    RestoreArchiveSchema,
    ChangePasswordSchema,
    UpdateMarketDataMappingsSchema,
    UpdateSymbolMappingsSchema,
    UpdateTimezoneSchema,
    UpdateDisplayTimezoneSchema,
    UpdateStartingEquitySchema,
)
from app.auth.service import AuthService
from app.utils.errors import AuthenticationError
from app.utils.errors import ValidationError

auth_service = AuthService()
register_schema = RegisterSchema()
login_schema = LoginSchema()
change_password_schema = ChangePasswordSchema()
update_timezone_schema = UpdateTimezoneSchema()
update_display_timezone_schema = UpdateDisplayTimezoneSchema()
update_starting_equity_schema = UpdateStartingEquitySchema()
update_symbol_mappings_schema = UpdateSymbolMappingsSchema()
update_market_data_mappings_schema = (
    UpdateMarketDataMappingsSchema()
)
restore_archive_schema = RestoreArchiveSchema()


def _apply_refresh_cookie(
    response,
    refresh_token: str,
):
    """Attach the persistent refresh cookie to a response."""

    response.set_cookie(
        current_app.config["AUTH_REFRESH_COOKIE_NAME"],
        refresh_token,
        max_age=current_app.config[
            "AUTH_REFRESH_COOKIE_MAX_AGE"
        ],
        httponly=True,
        secure=current_app.config[
            "AUTH_REFRESH_COOKIE_SECURE"
        ],
        samesite=current_app.config[
            "AUTH_REFRESH_COOKIE_SAMESITE"
        ],
        path=current_app.config["AUTH_REFRESH_COOKIE_PATH"],
    )
    return response


def _clear_refresh_cookie(response):
    """Clear the persistent refresh cookie from a response."""

    response.delete_cookie(
        current_app.config["AUTH_REFRESH_COOKIE_NAME"],
        path=current_app.config["AUTH_REFRESH_COOKIE_PATH"],
    )
    return response


def _build_auth_response(result: dict, status_code: int):
    """Return a public auth response and set the refresh cookie."""

    refresh_token = result["refresh_token"]
    payload = {
        "token": result["token"],
        "user": result["user"],
    }
    response = make_response(jsonify(payload), status_code)
    return _apply_refresh_cookie(response, refresh_token)


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
        user_agent=request.headers.get("User-Agent"),
    )
    return _build_auth_response(result, 201)


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
        user_agent=request.headers.get("User-Agent"),
    )
    return _build_auth_response(result, 200)


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    """Rotate the current refresh session and issue a new access token."""

    refresh_token = request.cookies.get(
        current_app.config["AUTH_REFRESH_COOKIE_NAME"],
        "",
    )
    if not refresh_token:
        response = make_response(
            jsonify(
                {
                    "error": {
                        "code": "AUTHENTICATIONERROR",
                        "message": "Session expired. Please log in again.",
                    }
                }
            ),
            401,
        )
        return _clear_refresh_cookie(response)

    try:
        result = auth_service.refresh_session(refresh_token)
    except AuthenticationError as error:
        response = make_response(
            jsonify(
                {
                    "error": {
                        "code": "AUTHENTICATIONERROR",
                        "message": error.message,
                    }
                }
            ),
            401,
        )
        return _clear_refresh_cookie(response)

    return _build_auth_response(result, 200)


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
def logout():
    """
    Logout (client-side token discard).

    Returns: {message}
    """
    result = auth_service.logout(
        request.cookies.get(
            current_app.config["AUTH_REFRESH_COOKIE_NAME"]
        )
    )
    response = make_response(jsonify(result), 200)
    return _clear_refresh_cookie(response)


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


@auth_bp.route("/display-timezone", methods=["PUT"])
@jwt_required()
def update_display_timezone():
    """
    Update the current user's display timezone.

    Expects JSON: {display_timezone}
    Returns: {user}
    """
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = update_display_timezone_schema.load(
            data
        )
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    user_id = get_jwt_identity()
    profile = auth_service.update_display_timezone(
        user_id=user_id,
        display_timezone=validated["display_timezone"],
    )
    return jsonify(profile), 200


@auth_bp.route("/starting-equity", methods=["PUT"])
@jwt_required()
def update_starting_equity():
    """
    Update the current user's starting equity.

    Expects JSON: {starting_equity}
    Returns: {user}
    """
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = update_starting_equity_schema.load(
            data
        )
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    user_id = get_jwt_identity()
    profile = auth_service.update_starting_equity(
        user_id=user_id,
        starting_equity=validated["starting_equity"],
    )
    return jsonify(profile), 200


@auth_bp.route("/symbol-mappings", methods=["PUT"])
@jwt_required()
def update_symbol_mappings():
    """
    Update the current user's symbol mappings.

    Expects JSON: {symbol_mappings}
    Returns: {user}
    """
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = update_symbol_mappings_schema.load(
            data
        )
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    user_id = get_jwt_identity()
    profile = auth_service.update_symbol_mappings(
        user_id=user_id,
        symbol_mappings=validated["symbol_mappings"],
    )
    return jsonify(profile), 200


@auth_bp.route("/market-data-mappings", methods=["PUT"])
@jwt_required()
def update_market_data_mappings():
    """
    Update the current user's market-data mappings.

    Expects JSON: {market_data_mappings}
    Returns: {user}
    """
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required.")

    try:
        validated = update_market_data_mappings_schema.load(
            data
        )
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    user_id = get_jwt_identity()
    profile = auth_service.update_market_data_mappings(
        user_id=user_id,
        market_data_mappings=validated[
            "market_data_mappings"
        ],
    )
    return jsonify(profile), 200


@auth_bp.route("/export", methods=["GET"])
@jwt_required()
def export_backup():
    """Export the authenticated user's portable backup archive."""
    user_id = get_jwt_identity()
    archive_buffer, filename = auth_service.export_backup(
        user_id
    )
    return send_file(
        archive_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )


@auth_bp.route("/restore", methods=["POST"])
@jwt_required()
def restore_backup():
    """Restore a portable backup archive into the current user."""
    archive_file = request.files.get("file")
    if archive_file is None:
        raise ValidationError("Backup archive file is required.")

    try:
        restore_archive_schema.load(
            {"filename": archive_file.filename or ""}
        )
    except MarshmallowError as e:
        raise ValidationError(
            "Validation failed.", details=e.messages
        )

    user_id = get_jwt_identity()
    result = auth_service.restore_backup(
        user_id, archive_file
    )
    return jsonify(result), 200
