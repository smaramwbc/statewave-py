"""Typed Statewave API client."""

from __future__ import annotations

from typing import Any

import httpx

from statewave.models import (
    CompileResult,
    ContextBundle,
    DeleteResult,
    Episode,
    SearchResult,
    Timeline,
)


class StatewaveClient:
    """Synchronous client for the Statewave API."""

    def __init__(self, base_url: str = "http://localhost:8100", timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self._base_url, timeout=timeout)

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

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
        resp = self._http.post(
            "/v1/episodes",
            json={
                "subject_id": subject_id,
                "source": source,
                "type": type,
                "payload": payload,
                "metadata": metadata or {},
                "provenance": provenance or {},
            },
        )
        resp.raise_for_status()
        return Episode.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Memories
    # ------------------------------------------------------------------

    def compile_memories(self, subject_id: str) -> CompileResult:
        resp = self._http.post("/v1/memories/compile", json={"subject_id": subject_id})
        resp.raise_for_status()
        return CompileResult.model_validate(resp.json())

    def search_memories(
        self,
        subject_id: str,
        *,
        kind: str | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> SearchResult:
        params: dict[str, Any] = {"subject_id": subject_id, "limit": limit}
        if kind:
            params["kind"] = kind
        if query:
            params["q"] = query
        resp = self._http.get("/v1/memories/search", params=params)
        resp.raise_for_status()
        return SearchResult.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def get_context(
        self,
        subject_id: str,
        task: str,
        *,
        max_tokens: int | None = None,
    ) -> ContextBundle:
        body: dict[str, Any] = {"subject_id": subject_id, "task": task}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        resp = self._http.post("/v1/context", json=body)
        resp.raise_for_status()
        return ContextBundle.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    def get_timeline(self, subject_id: str) -> Timeline:
        resp = self._http.get("/v1/timeline", params={"subject_id": subject_id})
        resp.raise_for_status()
        return Timeline.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Subjects
    # ------------------------------------------------------------------

    def delete_subject(self, subject_id: str) -> DeleteResult:
        resp = self._http.delete(f"/v1/subjects/{subject_id}")
        resp.raise_for_status()
        return DeleteResult.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
