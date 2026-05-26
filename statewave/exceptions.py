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


#: The set of refusal reasons the server returns from
#: ``POST /v1/receipts/{id}/replay`` when a receipt cannot be replayed.
#: Used by ``StatewaveUnreplayableError.reason`` so callers can
#: ``except StatewaveUnreplayableError as exc: if exc.reason == ...``
#: instead of parsing error code strings.
UNREPLAYABLE_REASONS = frozenset(
    {
        "missing_policy_snapshot",  # pre-v0.9 receipt — no snapshot was captured
        "nested_replay",            # the receipt is itself a replay (one level only)
        "invalid_snapshot",         # snapshot YAML failed to parse (tampering / corruption)
    }
)


class StatewaveUnreplayableError(StatewaveAPIError):
    """Raised when ``replay_receipt(...)`` is called on a receipt that
    cannot be replayed (v0.9+ #159).

    The server returns HTTP 422 with ``error.code = "unreplayable.<reason>"``
    in three cases; this exception extracts ``reason`` so callers can
    branch on it without string-matching the error code:

    - ``"missing_policy_snapshot"`` — pre-v0.9 receipt. No
      ``policy_snapshot`` was captured at emission and the replay
      engine cannot synthesise one retroactively. The receipt is
      still queryable / verifiable; only replay is refused.
    - ``"nested_replay"`` — the receipt is itself a replay
      (``mode == "as_of_replay"``). v0.9 ships one level only;
      replay the source receipt referenced by ``parent_receipt_id``
      instead.
    - ``"invalid_snapshot"`` — the snapshot's YAML failed to parse.
      Tampering or corruption at the column level (the signed body
      would have caught a body-level rewrite).

    The base ``StatewaveAPIError`` attributes (``status_code``,
    ``code``, ``message``, ``details``, ``request_id``) are
    populated as usual; ``reason`` is the parsed reason string.
    """

    def __init__(
        self,
        reason: str,
        *,
        status_code: int = 422,
        code: str | None = None,
        message: str = "",
        details: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        self.reason = reason
        super().__init__(
            status_code=status_code,
            code=code or f"unreplayable.{reason}",
            message=message or f"receipt is unreplayable: {reason}",
            details=details,
            request_id=request_id,
        )
