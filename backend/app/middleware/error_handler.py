"""Global error handler middleware."""

import traceback

from flask import current_app, jsonify

from app.utils.errors import AppError


def register_error_handlers(app):
    """
    Register global error handlers on the Flask app.

    Parameters:
        app: The Flask application instance.
    """

    @app.errorhandler(AppError)
    def handle_app_error(error):
        """Handle custom application errors."""
        current_app.logger.warning(
            "%s [%d]: %s %s",
            type(error).__name__,
            error.status_code,
            error.message,
            error.details if error.details else "",
        )
        response = {
            "error": {
                "code": type(error).__name__.upper(),
                "message": error.message,
            }
        }
        if error.details:
            response["error"]["details"] = error.details
        return jsonify(response), error.status_code

    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle 404 Not Found."""
        return jsonify({
            "error": {
                "code": "NOT_FOUND",
                "message": "Resource not found.",
            }
        }), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        """Handle 405 Method Not Allowed."""
        return jsonify({
            "error": {
                "code": "METHOD_NOT_ALLOWED",
                "message": "Method not allowed.",
            }
        }), 405

    @app.errorhandler(500)
    def handle_internal_error(error):
        """Handle 500 Internal Server Error."""
        current_app.logger.exception(
            "Unhandled exception: %s", error
        )
        response = {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal error occurred.",
            }
        }
        if current_app.debug:
            response["error"]["details"] = (
                traceback.format_exception(error)
            )
        return jsonify(response), 500
