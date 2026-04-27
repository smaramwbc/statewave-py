"""Typed Statewave API client — sync and async, with configurable retry."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from statewave.exceptions import (
    StatewaveAPIError,
    StatewaveConnectionError,
    StatewaveTimeoutError,
)
from statewave.models import (
    BatchCreateResult,
    CompileResult,
    ContextBundle,
    DeleteResult,
    Episode,
    ListSubjectsResult,
    SearchResult,
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
    """Parse a structured error response from the Statewave API."""
    try:
        body = resp.json()
        err = body.get("error", {})
        return StatewaveAPIError(
            status_code=resp.status_code,
            code=err.get("code", "unknown"),
            message=err.get("message", resp.reason_phrase or "Unknown error"),
            details=err.get("details"),
            request_id=err.get("request_id"),
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
    ) -> Episode:
        """Record a raw interaction episode."""
        return self._request(
            "POST",
            "/v1/episodes",
            json={
                "subject_id": subject_id,
                "source": source,
                "type": type,
                "payload": payload,
                "metadata": metadata or {},
                "provenance": provenance or {},
            },
            model=Episode,
        )

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
    ) -> ContextBundle:
        """Assemble a ranked, token-bounded context bundle."""
        body: dict[str, Any] = {"subject_id": subject_id, "task": task}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        return self._request("POST", "/v1/context", json=body, model=ContextBundle)

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

    def _request(self, method: str, path: str, *, model: type, json: Any = None, params: Any = None):
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
                return model.model_validate(resp.json())

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
    ) -> Episode:
        """Record a raw interaction episode."""
        return await self._request(
            "POST",
            "/v1/episodes",
            json={
                "subject_id": subject_id,
                "source": source,
                "type": type,
                "payload": payload,
                "metadata": metadata or {},
                "provenance": provenance or {},
            },
            model=Episode,
        )

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
    ) -> ContextBundle:
        """Assemble a ranked, token-bounded context bundle."""
        body: dict[str, Any] = {"subject_id": subject_id, "task": task}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        return await self._request("POST", "/v1/context", json=body, model=ContextBundle)

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

    async def _request(self, method: str, path: str, *, model: type, json: Any = None, params: Any = None):
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
                return model.model_validate(resp.json())

            if resp.status_code in self._retry.retry_on_status and attempt < self._retry.max_retries:
                retry_after = _parse_retry_after(resp)
                await asyncio.sleep(self._retry.delay_for_attempt(attempt, retry_after))
                continue

            raise _parse_error(resp)

        if last_exc:
            _handle_transport_error(last_exc)
        raise StatewaveConnectionError("Retry attempts exhausted")
