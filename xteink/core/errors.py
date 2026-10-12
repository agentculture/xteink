"""Domain errors raised by the core services (transport-agnostic)."""


class CoreError(Exception):
    """Base class for core errors."""


class NotFoundError(CoreError):
    """A referenced item, device or key does not exist."""


class ValidationError(CoreError):
    """Caller supplied invalid data."""


class AuthError(CoreError):
    """A key is unknown, malformed or revoked."""
