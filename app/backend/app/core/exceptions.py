class DomainError(Exception):
    """Base for errors raised by the service layer."""


class NotFoundError(DomainError):
    """Raised when a referenced entity does not exist."""
