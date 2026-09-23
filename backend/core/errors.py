from __future__ import annotations


class ApplicationError(Exception):
    status_code = 500
    error_code = "APPLICATION_ERROR"


class ValidationError(ApplicationError):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class NotFoundError(ApplicationError):
    status_code = 404
    error_code = "NOT_FOUND"


class AuthorizationError(ApplicationError):
    status_code = 403
    error_code = "AUTHORIZATION_ERROR"
