from __future__ import annotations


class AuthError(Exception):
    """Raised when Bearer token is missing, malformed, or fails verification."""


class MissingTokenError(AuthError):
    pass


class InvalidTokenError(AuthError):
    pass
