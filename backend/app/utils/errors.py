"""Custom exception classes and error handlers."""


class AppError(Exception):
    """Base application error."""

    status_code = 500

    def __init__(self, message: str, details: list = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class ValidationError(AppError):
    """Validation error — 400 Bad Request."""

    status_code = 400


class AuthenticationError(AppError):
    """Authentication error — 401 Unauthorized."""

    status_code = 401


class NotFoundError(AppError):
    """Resource not found — 404."""

    status_code = 404


class DuplicateImportError(AppError):
    """Duplicate import detected — 409 Conflict."""

    status_code = 409


class MarketDataError(AppError):
    """External market data fetch failure — 502."""

    status_code = 502
