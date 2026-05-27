"""Typed Statewave API client — sync and async, with configurable retry."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from statewave.exceptions import (
    UNREPLAYABLE_REASONS,
    StatewaveAPIError,
    StatewaveConnectionError,
    StatewaveTimeoutError,
    StatewaveUnreplayableError,
)
from statewave.models import (
    BatchCreateResult,
    CompileJob,
    CompileResult,
    ContextBundle,
    DeleteResult,
    Episode,
    Handoff,
    Health,
    ListSubjectsResult,
    Memory,
    Receipt,
    ReceiptList,
    ReceiptReplayResult,
    ReceiptVerifyResult,
    Resolution,
    SearchResult,
    SLASummary,
    Timeline,
)


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryConfig:
    """Retry configuration for transient failures.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries).
        backoff_base: Base delay in seconds for exponential backoff.
        backoff_max: Maximum delay cap in seconds.
        jitter: Whether to add random jitter to backoff delays.
        retry_on_status: HTTP status codes that trigger a retry.
    """

    max_retries: int = 3
    backoff_base: float = 0.5
    backoff_max: float = 30.0
    jitter: bool = True
    retry_on_status: frozenset[int] = frozenset({429, 500, 502, 503, 504})

    def delay_for_attempt(self, attempt: int, retry_after: float | None = None) -> float:
        """Calculate delay for a given attempt number (0-indexed)."""
        if retry_after is not None:
            return min(retry_after, self.backoff_max)
        delay = self.backoff_base * (2 ** attempt)
        delay = min(delay, self.backoff_max)
        if self.jitter:
            delay *= random.uniform(0.5, 1.5)
        return delay


#: No retries — fail immediately on any error.
NO_RETRY = RetryConfig(max_retries=0)

#: Default retry config — 3 retries with 0.5s base backoff.
DEFAULT_RETRY = RetryConfig()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_error(resp: httpx.Response) -> StatewaveAPIError:
    """Parse a structured error response from the Statewave API.

    Recognised structured codes:
      - ``unreplayable.<reason>`` (HTTP 422 from
        ``POST /v1/receipts/{id}/replay``) → ``StatewaveUnreplayableError``
        with ``.reason`` set so callers can branch without
        string-matching the error code.

    Anything else → the generic ``StatewaveAPIError``."""
    try:
        body = resp.json()
        err = body.get("error", {})
        code = err.get("code", "unknown")
        message = err.get("message", resp.reason_phrase or "Unknown error")
        details = err.get("details")
        request_id = err.get("request_id")

        # Promote unreplayable.* refusals into a dedicated exception so
        # callers can `except StatewaveUnreplayableError` and switch on
        # the structured reason. The server emits codes of the form
        # `unreplayable.<reason>` (see server/api/receipts.py).
        if (
            resp.status_code == 422
            and isinstance(code, str)
            and code.startswith("unreplayable.")
        ):
            reason = code[len("unreplayable."):]
            if reason in UNREPLAYABLE_REASONS:
                return StatewaveUnreplayableError(
                    reason=reason,
                    status_code=resp.status_code,
                    code=code,
                    message=message,
                    details=details,
                    request_id=request_id,
                )
        return StatewaveAPIError(
            status_code=resp.status_code,
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        )
    except Exception:
        return StatewaveAPIError(
            status_code=resp.status_code,
            code="unknown",
            message=resp.reason_phrase or f"HTTP {resp.status_code}",
        )


def _handle_transport_error(exc: Exception) -> None:
    """Convert httpx transport exceptions to Statewave exceptions."""
    if isinstance(exc, httpx.ConnectError):
        raise StatewaveConnectionError(str(exc)) from exc
    if isinstance(exc, httpx.TimeoutException):
        raise StatewaveTimeoutError(str(exc)) from exc
    raise StatewaveConnectionError(str(exc)) from exc


def _parse_retry_after(resp: httpx.Response) -> float | None:
    """Extract Retry-After header value as seconds, if present."""
    value = resp.headers.get("retry-after")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------

class StatewaveClient:
    """Synchronous client for the Statewave API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8100",
        timeout: float = 30.0,
        *,
        api_key: str | None = None,
        tenant_id: str | None = None,
        retry: RetryConfig | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._retry = retry if retry is not None else DEFAULT_RETRY
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        self._http = httpx.Client(base_url=self._base_url, timeout=timeout, headers=headers)

    # -- Episodes ----------------------------------------------------------

    def create_episode(
        self,
        subject_id: str,
        source: str,
        type: str,
        payload: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Episode:
        """Record a raw interaction episode.

        Pass ``session_id`` to attribute the episode to a specific session —
        the server's session-aware ranking uses it to surface active-session
        content in context bundles. Omit it for one-off events; the server
        treats absence as "no session pin" rather than auto-assigning.
        """
        body: dict[str, Any] = {
            "subject_id": subject_id,
            "source": source,
            "type": type,
            "payload": payload,
            "metadata": metadata or {},
            "provenance": provenance or {},
        }
        if session_id is not None:
            body["session_id"] = session_id
        return self._request("POST", "/v1/episodes", json=body, model=Episode)

    def create_episodes_batch(
        self,
        episodes: list[dict[str, Any]],
    ) -> BatchCreateResult:
        """Record multiple episodes in a single request (max 100)."""
        return self._request(
            "POST",
            "/v1/episodes/batch",
            json={"episodes": episodes},
            model=BatchCreateResult,
        )

    # -- Memories ----------------------------------------------------------

    def compile_memories(self, subject_id: str) -> CompileResult:
        """Compile memories from unprocessed episodes. Idempotent."""
        return self._request(
            "POST",
            "/v1/memories/compile",
            json={"subject_id": subject_id},
            model=CompileResult,
        )

    def compile_memories_async(self, subject_id: str) -> CompileJob:
        """Submit async compilation. Returns immediately with a job_id for polling.

        Use `get_compile_status()` to poll for completion.
        """
        resp = self._http.request(
            "POST", "/v1/memories/compile",
            json={"subject_id": subject_id, "async": True},
        )
        if not resp.is_success:
            raise _parse_error(resp)
        return CompileJob.model_validate(resp.json())

    def get_compile_status(self, job_id: str) -> CompileJob:
        """Poll the status of an async compile job."""
        return self._request(
            "GET", f"/v1/memories/compile/{job_id}", model=CompileJob,
        )

    def compile_memories_wait(
        self,
        subject_id: str,
        *,
        poll_interval: float = 0.5,
        timeout: float = 60.0,
    ) -> CompileJob:
        """Submit async compilation and poll until completion or timeout.

        Convenience method that combines submit + polling.
        Raises TimeoutError if job doesn't complete within timeout.
        """
        job = self.compile_memories_async(subject_id)
        elapsed = 0.0
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval
            job = self.get_compile_status(job.job_id)
            if job.status in ("completed", "failed"):
                return job
        raise TimeoutError(f"Compile job {job.job_id} did not complete within {timeout}s")

    def search_memories(
        self,
        subject_id: str,
        *,
        kind: str | None = None,
        query: str | None = None,
        semantic: bool = False,
        limit: int = 20,
    ) -> SearchResult:
        """Search memories by kind, text query, or semantic similarity."""
        params: dict[str, Any] = {"subject_id": subject_id, "limit": limit}
        if kind:
            params["kind"] = kind
        if query:
            params["q"] = query
        if semantic:
            params["semantic"] = "true"
        return self._request("GET", "/v1/memories/search", params=params, model=SearchResult)

    # -- Context -----------------------------------------------------------

    def get_context(
        self,
        subject_id: str,
        task: str,
        *,
        max_tokens: int | None = None,
        session_id: str | None = None,
        emit_receipt: bool | None = None,
        query_id: str | None = None,
        task_id: str | None = None,
        parent_receipt_id: str | None = None,
        caller_id: str | None = None,
        caller_type: str | None = None,
    ) -> ContextBundle:
        """Assemble a ranked, token-bounded context bundle.

        `caller_id` and `caller_type` are consumed by the
        sensitivity-label policy layer (#50). When the tenant config
        sets `require_caller_identity: true`, both are mandatory.

        When `emit_receipt=True` (or the tenant's receipts config is
        `always`), the returned bundle carries a `receipt_id` that can
        be fetched via `get_receipt()`. See `Receipt` for the body
        schema.
        """
        body: dict[str, Any] = {"subject_id": subject_id, "task": task}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if session_id is not None:
            body["session_id"] = session_id
        if emit_receipt is not None:
            body["emit_receipt"] = emit_receipt
        if query_id is not None:
            body["query_id"] = query_id
        if task_id is not None:
            body["task_id"] = task_id
        if parent_receipt_id is not None:
            body["parent_receipt_id"] = parent_receipt_id
        if caller_id is not None:
            body["caller_id"] = caller_id
        if caller_type is not None:
            body["caller_type"] = caller_type
        return self._request("POST", "/v1/context", json=body, model=ContextBundle)

    # -- Memory labels (#50) ----------------------------------------------

    def set_memory_labels(
        self,
        memory_id: str,
        labels: list[str],
    ) -> Memory:
        """Replace a memory's sensitivity_labels with the supplied list.

        Labels are deduplicated, lowercased, and trimmed server-side
        — the policy evaluator does exact match so normalizing at the
        write boundary is the only place to do it safely. An empty
        list clears all labels (memory becomes untagged → policy
        default-allow).
        """
        return self._request(
            "PATCH",
            f"/v1/memories/{memory_id}/labels",
            json={"sensitivity_labels": labels},
            model=Memory,
        )

    def get_context_string(
        self,
        subject_id: str,
        task: str,
        *,
        max_tokens: int | None = None,
    ) -> str:
        """Return just the assembled context string, ready to inject into a prompt."""
        bundle = self.get_context(subject_id, task, max_tokens=max_tokens)
        return bundle.assembled_context

    # -- Receipts ----------------------------------------------------------

    def get_receipt(self, receipt_id: str) -> Receipt:
        """Fetch a single state-assembly receipt by ULID."""
        return self._request("GET", f"/v1/receipts/{receipt_id}", model=Receipt)

    def list_receipts(
        self,
        subject_id: str,
        *,
        since: str | None = None,
        until: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ReceiptList:
        """List receipts for a subject, newest first. Cursor-paginated —
        pass the previous response's `next_cursor` to fetch the next page."""
        params: dict[str, Any] = {"subject_id": subject_id, "limit": limit}
        if since is not None:
            params["since"] = since
        if until is not None:
            params["until"] = until
        if cursor is not None:
            params["cursor"] = cursor
        return self._request("GET", "/v1/receipts", params=params, model=ReceiptList)

    def verify_receipt(self, receipt_id: str) -> ReceiptVerifyResult:
        """Verify the HMAC signature on a stored receipt (v0.9+ #157).

        Calls ``GET /v1/receipts/{receipt_id}/verify``. Returns a
        :class:`ReceiptVerifyResult` with ``valid`` ∈ ``{True, False, None}``:

        - ``True`` → signature matches the canonical body
          (``reason == "ok"``).
        - ``False`` → signature does not cover the body
          (``reason == "signature_mismatch"``).
        - ``None`` → verdict could not be determined; ``reason`` is
          one of ``"no_signature"`` (unsigned receipt — pre-v0.9 or
          tenant didn't opt in), ``"key_unavailable"`` (the key id
          rotated out of operator config), or
          ``"unsupported_algorithm"`` (forward-compat).

        Comparison is constant-time on the server side. The signing
        key bytes never appear on the response — only the public
        ``key_id`` is echoed.

        Raises :class:`StatewaveAPIError` on 404 (receipt not found
        or belongs to a different tenant — indistinguishable on the
        wire) and other non-2xx responses.
        """
        return self._request(
            "GET",
            f"/v1/receipts/{receipt_id}/verify",
            model=ReceiptVerifyResult,
        )

    def replay_receipt(self, receipt_id: str) -> ReceiptReplayResult:
        """Re-run the original retrieval against current memories using
        the original policy bundle captured in the receipt's
        ``policy_snapshot`` (v0.9+ #159).

        Calls ``POST /v1/receipts/{receipt_id}/replay``. Emits a new
        ``mode="as_of_replay"`` receipt with ``parent_receipt_id``
        pointing at the source; the original receipt is **never**
        modified. Returns a :class:`ReceiptReplayResult` containing
        the new ``replay_receipt_id`` plus a structural diff
        envelope (added/removed selected entries, filter changes,
        context-hash diff).

        Semantic: current code + original policy. Replay is *not*
        byte-for-byte reproduction; memories that were added,
        tombstoned, or supersession-resolved between the original
        emission and now will appear in the diff. See
        ``docs/replay.md`` in the server repo for the design.

        Raises :class:`StatewaveUnreplayableError` (HTTP 422) when:

        - ``reason == "missing_policy_snapshot"`` — pre-v0.9 receipt.
        - ``reason == "nested_replay"`` — the receipt is itself a
          replay (v0.9 ships one level only).
        - ``reason == "invalid_snapshot"`` — snapshot YAML failed
          to parse (tampering / corruption).

        Raises :class:`StatewaveAPIError` on 404 and other non-2xx
        responses.
        """
        return self._request(
            "POST",
            f"/v1/receipts/{receipt_id}/replay",
            model=ReceiptReplayResult,
        )

    # -- Support: health, SLA, handoff, resolutions ------------------------

    def get_health(self, subject_id: str) -> Health:
        """Compute the customer health score (0-100) for a subject.

        Returns the score, the state bucket (``healthy`` | ``watch`` |
        ``at_risk``), and the explainable factors that drove it.
        """
        return self._request(
            "GET", f"/v1/subjects/{subject_id}/health", model=Health,
        )

    def get_sla(
        self,
        subject_id: str,
        *,
        first_response_threshold_minutes: float | None = None,
        resolution_threshold_hours: float | None = None,
    ) -> SLASummary:
        """Compute SLA metrics for a subject.

        Aggregates first-response and resolution times across the
        subject's sessions and flags breaches against the supplied
        thresholds. Both thresholds fall back to the server defaults
        (5 minutes / 24 hours) when omitted.
        """
        params: dict[str, Any] = {}
        if first_response_threshold_minutes is not None:
            params["first_response_threshold_minutes"] = first_response_threshold_minutes
        if resolution_threshold_hours is not None:
            params["resolution_threshold_hours"] = resolution_threshold_hours
        return self._request(
            "GET", f"/v1/subjects/{subject_id}/sla", params=params, model=SLASummary,
        )

    def create_handoff(
        self,
        subject_id: str,
        session_id: str,
        *,
        reason: str | None = None,
        max_tokens: int | None = None,
        emit_receipt: bool | None = None,
        query_id: str | None = None,
        task_id: str | None = None,
        parent_receipt_id: str | None = None,
        caller_id: str | None = None,
        caller_type: str | None = None,
    ) -> Handoff:
        """Generate a handoff context pack for escalation or shift change.

        Produces a structured escalation brief; ``handoff_notes`` is a
        pre-rendered markdown brief ready for human or LLM use.

        ``caller_id`` and ``caller_type`` are consumed by the
        sensitivity-label policy layer (#50); when the tenant config
        sets ``require_caller_identity: true``, both are mandatory.
        """
        body: dict[str, Any] = {"subject_id": subject_id, "session_id": session_id}
        if reason is not None:
            body["reason"] = reason
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if emit_receipt is not None:
            body["emit_receipt"] = emit_receipt
        if query_id is not None:
            body["query_id"] = query_id
        if task_id is not None:
            body["task_id"] = task_id
        if parent_receipt_id is not None:
            body["parent_receipt_id"] = parent_receipt_id
        if caller_id is not None:
            body["caller_id"] = caller_id
        if caller_type is not None:
            body["caller_type"] = caller_type
        return self._request("POST", "/v1/handoff", json=body, model=Handoff)

    def create_resolution(
        self,
        subject_id: str,
        session_id: str,
        *,
        status: str = "open",
        resolution_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Resolution:
        """Create or update a resolution record for a support session.

        Upserts by ``subject_id`` + ``session_id``. ``status`` is one of
        ``open``, ``resolved``, or ``unresolved``.
        """
        body: dict[str, Any] = {
            "subject_id": subject_id,
            "session_id": session_id,
            "status": status,
        }
        if resolution_summary is not None:
            body["resolution_summary"] = resolution_summary
        if metadata is not None:
            body["metadata"] = metadata
        return self._request("POST", "/v1/resolutions", json=body, model=Resolution)

    def list_resolutions(
        self,
        subject_id: str,
        *,
        status: str | None = None,
    ) -> list[Resolution]:
        """List resolution records for a subject.

        Optionally filter to a single ``status`` (``open`` | ``resolved``
        | ``unresolved``).
        """
        params: dict[str, Any] = {"subject_id": subject_id}
        if status is not None:
            params["status"] = status
        return self._request(
            "GET", "/v1/resolutions", params=params, model=Resolution, is_list=True,
        )

    # -- Timeline ----------------------------------------------------------

    def get_timeline(self, subject_id: str) -> Timeline:
        """Get chronological subject timeline."""
        return self._request(
            "GET", "/v1/timeline", params={"subject_id": subject_id}, model=Timeline
        )

    # -- Subjects ----------------------------------------------------------

    def delete_subject(self, subject_id: str) -> DeleteResult:
        """Permanently delete all data for a subject."""
        return self._request("DELETE", f"/v1/subjects/{subject_id}", model=DeleteResult)

    def list_subjects(self, *, limit: int = 50, offset: int = 0) -> ListSubjectsResult:
        """List all known subjects with episode/memory counts."""
        return self._request(
            "GET", "/v1/subjects",
            params={"limit": limit, "offset": offset},
            model=ListSubjectsResult,
        )

    # -- Lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # -- Internal ----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        model: type,
        json: Any = None,
        params: Any = None,
        is_list: bool = False,
    ):
        last_exc: Exception | None = None
        for attempt in range(self._retry.max_retries + 1):
            try:
                resp = self._http.request(method, path, json=json, params=params)
            except httpx.HTTPStatusError:
                raise
            except Exception as exc:
                # Connection/timeout error — retryable
                if attempt < self._retry.max_retries:
                    last_exc = exc
                    time.sleep(self._retry.delay_for_attempt(attempt))
                    continue
                _handle_transport_error(exc)

            if resp.is_success:
                data = resp.json()
                if is_list:
                    return [model.model_validate(item) for item in data]
                return model.model_validate(data)

            # Check if retryable status
            if resp.status_code in self._retry.retry_on_status and attempt < self._retry.max_retries:
                retry_after = _parse_retry_after(resp)
                time.sleep(self._retry.delay_for_attempt(attempt, retry_after))
                continue

            raise _parse_error(resp)

        # Should not reach here, but just in case
        if last_exc:
            _handle_transport_error(last_exc)
        raise StatewaveConnectionError("Retry attempts exhausted")


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------

class AsyncStatewaveClient:
    """Async client for the Statewave API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8100",
        timeout: float = 30.0,
        *,
        api_key: str | None = None,
        tenant_id: str | None = None,
        retry: RetryConfig | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._retry = retry if retry is not None else DEFAULT_RETRY
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=timeout, headers=headers)

    # -- Episodes ----------------------------------------------------------

    async def create_episode(
        self,
        subject_id: str,
        source: str,
        type: str,
        payload: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Episode:
        """Record a raw interaction episode.

        Pass ``session_id`` to attribute the episode to a specific session —
        the server's session-aware ranking uses it to surface active-session
        content in context bundles. Omit it for one-off events; the server
        treats absence as "no session pin" rather than auto-assigning.
        """
        body: dict[str, Any] = {
            "subject_id": subject_id,
            "source": source,
            "type": type,
            "payload": payload,
            "metadata": metadata or {},
            "provenance": provenance or {},
        }
        if session_id is not None:
            body["session_id"] = session_id
        return await self._request("POST", "/v1/episodes", json=body, model=Episode)

    async def create_episodes_batch(
        self,
        episodes: list[dict[str, Any]],
    ) -> BatchCreateResult:
        """Record multiple episodes in a single request (max 100)."""
        return await self._request(
            "POST",
            "/v1/episodes/batch",
            json={"episodes": episodes},
            model=BatchCreateResult,
        )

    # -- Memories ----------------------------------------------------------

    async def compile_memories(self, subject_id: str) -> CompileResult:
        """Compile memories from unprocessed episodes. Idempotent."""
        return await self._request(
            "POST",
            "/v1/memories/compile",
            json={"subject_id": subject_id},
            model=CompileResult,
        )

    async def compile_memories_async(self, subject_id: str) -> CompileJob:
        """Submit async compilation. Returns immediately with a job_id for polling."""
        resp = await self._http.request(
            "POST", "/v1/memories/compile",
            json={"subject_id": subject_id, "async": True},
        )
        if not resp.is_success:
            raise _parse_error(resp)
        return CompileJob.model_validate(resp.json())

    async def get_compile_status(self, job_id: str) -> CompileJob:
        """Poll the status of an async compile job."""
        return await self._request(
            "GET", f"/v1/memories/compile/{job_id}", model=CompileJob,
        )

    async def compile_memories_wait(
        self,
        subject_id: str,
        *,
        poll_interval: float = 0.5,
        timeout: float = 60.0,
    ) -> CompileJob:
        """Submit async compilation and poll until completion or timeout."""
        import asyncio as _asyncio

        job = await self.compile_memories_async(subject_id)
        elapsed = 0.0
        while elapsed < timeout:
            await _asyncio.sleep(poll_interval)
            elapsed += poll_interval
            job = await self.get_compile_status(job.job_id)
            if job.status in ("completed", "failed"):
                return job
        raise TimeoutError(f"Compile job {job.job_id} did not complete within {timeout}s")

    async def search_memories(
        self,
        subject_id: str,
        *,
        kind: str | None = None,
        query: str | None = None,
        semantic: bool = False,
        limit: int = 20,
    ) -> SearchResult:
        """Search memories by kind, text query, or semantic similarity."""
        params: dict[str, Any] = {"subject_id": subject_id, "limit": limit}
        if kind:
            params["kind"] = kind
        if query:
            params["q"] = query
        if semantic:
            params["semantic"] = "true"
        return await self._request("GET", "/v1/memories/search", params=params, model=SearchResult)

    # -- Context -----------------------------------------------------------

    async def get_context(
        self,
        subject_id: str,
        task: str,
        *,
        max_tokens: int | None = None,
        session_id: str | None = None,
        emit_receipt: bool | None = None,
        query_id: str | None = None,
        task_id: str | None = None,
        parent_receipt_id: str | None = None,
        caller_id: str | None = None,
        caller_type: str | None = None,
    ) -> ContextBundle:
        """Assemble a ranked, token-bounded context bundle.

        `caller_id` and `caller_type` are consumed by the
        sensitivity-label policy layer (#50). When the tenant config
        sets `require_caller_identity: true`, both are mandatory.

        When `emit_receipt=True` (or the tenant's receipts config is
        `always`), the returned bundle carries a `receipt_id` that can
        be fetched via `get_receipt()`.
        """
        body: dict[str, Any] = {"subject_id": subject_id, "task": task}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if session_id is not None:
            body["session_id"] = session_id
        if emit_receipt is not None:
            body["emit_receipt"] = emit_receipt
        if query_id is not None:
            body["query_id"] = query_id
        if task_id is not None:
            body["task_id"] = task_id
        if parent_receipt_id is not None:
            body["parent_receipt_id"] = parent_receipt_id
        if caller_id is not None:
            body["caller_id"] = caller_id
        if caller_type is not None:
            body["caller_type"] = caller_type
        return await self._request("POST", "/v1/context", json=body, model=ContextBundle)

    async def set_memory_labels(
        self,
        memory_id: str,
        labels: list[str],
    ) -> Memory:
        """Replace a memory's sensitivity_labels (#50)."""
        return await self._request(
            "PATCH",
            f"/v1/memories/{memory_id}/labels",
            json={"sensitivity_labels": labels},
            model=Memory,
        )

    async def get_context_string(
        self,
        subject_id: str,
        task: str,
        *,
        max_tokens: int | None = None,
    ) -> str:
        """Return just the assembled context string, ready to inject into a prompt."""
        bundle = await self.get_context(subject_id, task, max_tokens=max_tokens)
        return bundle.assembled_context

    # -- Receipts ----------------------------------------------------------

    async def get_receipt(self, receipt_id: str) -> Receipt:
        """Fetch a single state-assembly receipt by ULID."""
        return await self._request(
            "GET", f"/v1/receipts/{receipt_id}", model=Receipt
        )

    async def list_receipts(
        self,
        subject_id: str,
        *,
        since: str | None = None,
        until: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ReceiptList:
        """List receipts for a subject, newest first. Cursor-paginated."""
        params: dict[str, Any] = {"subject_id": subject_id, "limit": limit}
        if since is not None:
            params["since"] = since
        if until is not None:
            params["until"] = until
        if cursor is not None:
            params["cursor"] = cursor
        return await self._request("GET", "/v1/receipts", params=params, model=ReceiptList)

    async def verify_receipt(self, receipt_id: str) -> ReceiptVerifyResult:
        """Async — verify the HMAC signature on a stored receipt (v0.9+ #157).
        See :meth:`StatewaveClient.verify_receipt` for the full contract."""
        return await self._request(
            "GET",
            f"/v1/receipts/{receipt_id}/verify",
            model=ReceiptVerifyResult,
        )

    async def replay_receipt(self, receipt_id: str) -> ReceiptReplayResult:
        """Async — replay a receipt against current memories with the
        receipt's original policy bundle (v0.9+ #159). See
        :meth:`StatewaveClient.replay_receipt` for the full contract,
        including the :class:`StatewaveUnreplayableError` cases."""
        return await self._request(
            "POST",
            f"/v1/receipts/{receipt_id}/replay",
            model=ReceiptReplayResult,
        )

    # -- Support: health, SLA, handoff, resolutions ------------------------

    async def get_health(self, subject_id: str) -> Health:
        """Compute the customer health score (0-100) for a subject.

        Returns the score, the state bucket (``healthy`` | ``watch`` |
        ``at_risk``), and the explainable factors that drove it.
        """
        return await self._request(
            "GET", f"/v1/subjects/{subject_id}/health", model=Health,
        )

    async def get_sla(
        self,
        subject_id: str,
        *,
        first_response_threshold_minutes: float | None = None,
        resolution_threshold_hours: float | None = None,
    ) -> SLASummary:
        """Compute SLA metrics for a subject.

        Aggregates first-response and resolution times across the
        subject's sessions and flags breaches against the supplied
        thresholds. Both thresholds fall back to the server defaults
        (5 minutes / 24 hours) when omitted.
        """
        params: dict[str, Any] = {}
        if first_response_threshold_minutes is not None:
            params["first_response_threshold_minutes"] = first_response_threshold_minutes
        if resolution_threshold_hours is not None:
            params["resolution_threshold_hours"] = resolution_threshold_hours
        return await self._request(
            "GET", f"/v1/subjects/{subject_id}/sla", params=params, model=SLASummary,
        )

    async def create_handoff(
        self,
        subject_id: str,
        session_id: str,
        *,
        reason: str | None = None,
        max_tokens: int | None = None,
        emit_receipt: bool | None = None,
        query_id: str | None = None,
        task_id: str | None = None,
        parent_receipt_id: str | None = None,
        caller_id: str | None = None,
        caller_type: str | None = None,
    ) -> Handoff:
        """Generate a handoff context pack for escalation or shift change.

        Produces a structured escalation brief; ``handoff_notes`` is a
        pre-rendered markdown brief ready for human or LLM use.

        ``caller_id`` and ``caller_type`` are consumed by the
        sensitivity-label policy layer (#50); when the tenant config
        sets ``require_caller_identity: true``, both are mandatory.
        """
        body: dict[str, Any] = {"subject_id": subject_id, "session_id": session_id}
        if reason is not None:
            body["reason"] = reason
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if emit_receipt is not None:
            body["emit_receipt"] = emit_receipt
        if query_id is not None:
            body["query_id"] = query_id
        if task_id is not None:
            body["task_id"] = task_id
        if parent_receipt_id is not None:
            body["parent_receipt_id"] = parent_receipt_id
        if caller_id is not None:
            body["caller_id"] = caller_id
        if caller_type is not None:
            body["caller_type"] = caller_type
        return await self._request("POST", "/v1/handoff", json=body, model=Handoff)

    async def create_resolution(
        self,
        subject_id: str,
        session_id: str,
        *,
        status: str = "open",
        resolution_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Resolution:
        """Create or update a resolution record for a support session.

        Upserts by ``subject_id`` + ``session_id``. ``status`` is one of
        ``open``, ``resolved``, or ``unresolved``.
        """
        body: dict[str, Any] = {
            "subject_id": subject_id,
            "session_id": session_id,
            "status": status,
        }
        if resolution_summary is not None:
            body["resolution_summary"] = resolution_summary
        if metadata is not None:
            body["metadata"] = metadata
        return await self._request("POST", "/v1/resolutions", json=body, model=Resolution)

    async def list_resolutions(
        self,
        subject_id: str,
        *,
        status: str | None = None,
    ) -> list[Resolution]:
        """List resolution records for a subject.

        Optionally filter to a single ``status`` (``open`` | ``resolved``
        | ``unresolved``).
        """
        params: dict[str, Any] = {"subject_id": subject_id}
        if status is not None:
            params["status"] = status
        return await self._request(
            "GET", "/v1/resolutions", params=params, model=Resolution, is_list=True,
        )

    # -- Timeline ----------------------------------------------------------

    async def get_timeline(self, subject_id: str) -> Timeline:
        """Get chronological subject timeline."""
        return await self._request(
            "GET", "/v1/timeline", params={"subject_id": subject_id}, model=Timeline
        )

    # -- Subjects ----------------------------------------------------------

    async def delete_subject(self, subject_id: str) -> DeleteResult:
        """Permanently delete all data for a subject."""
        return await self._request("DELETE", f"/v1/subjects/{subject_id}", model=DeleteResult)

    async def list_subjects(self, *, limit: int = 50, offset: int = 0) -> ListSubjectsResult:
        """List all known subjects with episode/memory counts."""
        return await self._request(
            "GET", "/v1/subjects",
            params={"limit": limit, "offset": offset},
            model=ListSubjectsResult,
        )

    # -- Lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    # -- Internal ----------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        model: type,
        json: Any = None,
        params: Any = None,
        is_list: bool = False,
    ):
        import asyncio

        last_exc: Exception | None = None
        for attempt in range(self._retry.max_retries + 1):
            try:
                resp = await self._http.request(method, path, json=json, params=params)
            except Exception as exc:
                if attempt < self._retry.max_retries:
                    last_exc = exc
                    await asyncio.sleep(self._retry.delay_for_attempt(attempt))
                    continue
                _handle_transport_error(exc)

            if resp.is_success:
                data = resp.json()
                if is_list:
                    return [model.model_validate(item) for item in data]
                return model.model_validate(data)

            if resp.status_code in self._retry.retry_on_status and attempt < self._retry.max_retries:
                retry_after = _parse_retry_after(resp)
                await asyncio.sleep(self._retry.delay_for_attempt(attempt, retry_after))
                continue

            raise _parse_error(resp)

        if last_exc:
            _handle_transport_error(last_exc)
        raise StatewaveConnectionError("Retry attempts exhausted")
