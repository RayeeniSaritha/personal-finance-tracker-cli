"""
Custom domain exception hierarchy for Personal Finance Tracker.
"""


class FinanceTrackerError(Exception):
    """Base exception for all domain-specific errors in Finance Tracker."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class ValidationError(FinanceTrackerError):
    """Raised when user input or domain object data fails validation constraints."""

    pass


class StorageError(FinanceTrackerError):
    """Raised when file I/O, schema verification, or atomic write operations fail."""

    pass


class NotFoundError(FinanceTrackerError):
    """Raised when a requested resource (e.g. transaction ID) cannot be located."""

    pass


class BudgetExceededError(FinanceTrackerError):
    """Raised when an expense action exceeds a configured budget threshold."""

    pass
