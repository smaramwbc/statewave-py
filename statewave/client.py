"""Typed Statewave API client — sync and async."""

from __future__ import annotations

from typing import Any

import httpx

from statewave.exceptions import (
    StatewaveAPIError,
    StatewaveConnectionError,
    StatewaveTimeoutError,
)
from statewave.models import (
    CompileResult,
    ContextBundle,
    DeleteResult,
    Episode,
    SearchResult,
    Timeline,
)


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


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------

class StatewaveClient:
    """Synchronous client for the Statewave API."""

    def __init__(self, base_url: str = "http://localhost:8100", timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self._base_url, timeout=timeout)

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
        limit: int = 20,
    ) -> SearchResult:
        """Search memories by kind or text query."""
        params: dict[str, Any] = {"subject_id": subject_id, "limit": limit}
        if kind:
            params["kind"] = kind
        if query:
            params["q"] = query
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

    # -- Lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # -- Internal ----------------------------------------------------------

    def _request(self, method: str, path: str, *, model: type, json: Any = None, params: Any = None):
        try:
            resp = self._http.request(method, path, json=json, params=params)
        except httpx.HTTPStatusError:
            raise
        except Exception as exc:
            _handle_transport_error(exc)
        if not resp.is_success:
            raise _parse_error(resp)
        return model.model_validate(resp.json())


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------

class AsyncStatewaveClient:
    """Async client for the Statewave API."""

    def __init__(self, base_url: str = "http://localhost:8100", timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

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
        limit: int = 20,
    ) -> SearchResult:
        """Search memories by kind or text query."""
        params: dict[str, Any] = {"subject_id": subject_id, "limit": limit}
        if kind:
            params["kind"] = kind
        if query:
            params["q"] = query
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

    # -- Lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    # -- Internal ----------------------------------------------------------

    async def _request(self, method: str, path: str, *, model: type, json: Any = None, params: Any = None):
        try:
            resp = await self._http.request(method, path, json=json, params=params)
        except Exception as exc:
            _handle_transport_error(exc)
        if not resp.is_success:
            raise _parse_error(resp)
        return model.model_validate(resp.json())
