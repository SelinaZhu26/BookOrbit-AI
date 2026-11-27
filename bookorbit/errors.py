"""Application errors.

Services raise these; the GUI turns them into the messages listed in the
"Alternative Flow" of each use case.
"""
from __future__ import annotations


class BookOrbitError(Exception):
    """Base class. ``message`` is safe to show to the user."""

    def __init__(self, message: str, field: str | None = None, **extra):
        super().__init__(message)
        self.message = message
        self.field = field
        self.extra = extra


class ValidationError(BookOrbitError):
    """Input failed a check. ``fields`` maps field name -> reason."""

    def __init__(self, message: str, fields: dict[str, str] | None = None):
        super().__init__(message)
        self.fields = fields or {}


class NotFoundError(BookOrbitError):
    pass


class PermissionDenied(BookOrbitError):
    pass


class AccountSuspended(BookOrbitError):
    pass


class BiometricError(BookOrbitError):
    """Face pipeline problem (no face, several faces, models missing, no camera)."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class StorageError(BookOrbitError):
    pass