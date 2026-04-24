"""Statewave SDK exceptions."""

from __future__ import annotations

from typing import Any


class StatewaveError(Exception):
    """Base exception for all Statewave SDK errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class StatewaveAPIError(StatewaveError):
    """Raised when the Statewave API returns a non-2xx response.

    Attributes:
        status_code: HTTP status code from the server.
        code: Error code from the structured error response (e.g. "validation_error").
        message: Human-readable error message.
        details: Optional additional error details.
        request_id: Request ID from the server, if available.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.details = details
        self.request_id = request_id
        super().__init__(f"[{status_code}] {code}: {message}")


class StatewaveConnectionError(StatewaveError):
    """Raised when the SDK cannot connect to the Statewave server."""

    def __init__(self, message: str = "Cannot connect to Statewave server") -> None:
        super().__init__(message)


class StatewaveTimeoutError(StatewaveError):
    """Raised when a request to the Statewave server times out."""

    def __init__(self, message: str = "Request timed out") -> None:
        super().__init__(message)
