"""Tests for the Statewave Python SDK."""

from __future__ import annotations

import pytest
import httpx
from unittest.mock import MagicMock

from statewave.models import (
    Episode,
    Memory,
    CompileResult,
    ContextBundle,
    Timeline,
    DeleteResult,
)
from statewave.exceptions import (
    StatewaveAPIError,
    StatewaveConnectionError,
    StatewaveTimeoutError,
    StatewaveError,
)
from statewave.client import _parse_error, _handle_transport_error


# ---------------------------------------------------------------------------
# Model parsing
# ---------------------------------------------------------------------------

def test_episode_parse():
    data = {
        "id": "00000000-0000-0000-0000-000000000001",
        "subject_id": "user-1",
        "source": "chat",
        "type": "conversation",
        "payload": {"text": "hello"},
        "metadata": {},
        "provenance": {},
        "created_at": "2025-01-01T00:00:00Z",
    }
    ep = Episode.model_validate(data)
    assert ep.subject_id == "user-1"
    assert ep.source == "chat"


def test_memory_parse():
    data = {
        "id": "00000000-0000-0000-0000-000000000002",
        "subject_id": "user-1",
        "kind": "profile_fact",
        "content": "Name is Alice",
        "summary": "Name is Alice",
        "confidence": 0.9,
        "valid_from": "2025-01-01T00:00:00Z",
        "valid_to": None,
        "source_episode_ids": ["00000000-0000-0000-0000-000000000001"],
        "metadata": {},
        "status": "active",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }
    mem = Memory.model_validate(data)
    assert mem.kind == "profile_fact"
    assert len(mem.source_episode_ids) == 1


def test_compile_result_parse():
    data = {
        "subject_id": "user-1",
        "memories_created": 2,
        "memories": [],
    }
    result = CompileResult.model_validate(data)
    assert result.memories_created == 2


def test_context_bundle_parse():
    data = {
        "subject_id": "user-1",
        "task": "help user",
        "facts": [],
        "episodes": [],
        "procedures": [],
        "provenance": {"fact_ids": [], "summary_ids": [], "episode_ids": []},
        "assembled_context": "## Task\nhelp user\n",
        "token_estimate": 5,
    }
    ctx = ContextBundle.model_validate(data)
    assert ctx.token_estimate == 5
    assert ctx.task == "help user"
    assert ctx.assembled_context == "## Task\nhelp user\n"


def test_timeline_parse():
    data = {"subject_id": "user-1", "episodes": [], "memories": []}
    tl = Timeline.model_validate(data)
    assert tl.subject_id == "user-1"


def test_delete_result_parse():
    data = {"subject_id": "user-1", "episodes_deleted": 3, "memories_deleted": 5}
    dr = DeleteResult.model_validate(data)
    assert dr.episodes_deleted == 3


# ---------------------------------------------------------------------------
# Error parsing
# ---------------------------------------------------------------------------

def test_parse_error_structured():
    resp = MagicMock()
    resp.status_code = 422
    resp.json.return_value = {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed",
            "details": [{"loc": ["body", "subject_id"], "msg": "required"}],
            "request_id": "abc123",
        }
    }
    err = _parse_error(resp)
    assert isinstance(err, StatewaveAPIError)
    assert err.status_code == 422
    assert err.code == "validation_error"
    assert err.request_id == "abc123"
    assert err.details is not None


def test_parse_error_unstructured():
    resp = MagicMock()
    resp.status_code = 500
    resp.json.side_effect = ValueError("not json")
    resp.reason_phrase = "Internal Server Error"
    err = _parse_error(resp)
    assert err.status_code == 500
    assert err.code == "unknown"


def test_handle_connect_error():
    with pytest.raises(StatewaveConnectionError):
        _handle_transport_error(httpx.ConnectError("refused"))


def test_handle_timeout_error():
    with pytest.raises(StatewaveTimeoutError):
        _handle_transport_error(httpx.ReadTimeout("timed out"))


def test_handle_generic_error():
    with pytest.raises(StatewaveConnectionError):
        _handle_transport_error(OSError("network down"))


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

def test_all_exceptions_inherit_from_base():
    assert issubclass(StatewaveAPIError, StatewaveError)
    assert issubclass(StatewaveConnectionError, StatewaveError)
    assert issubclass(StatewaveTimeoutError, StatewaveError)


def test_api_error_str():
    err = StatewaveAPIError(
        status_code=422, code="validation_error", message="bad request"
    )
    assert "422" in str(err)
    assert "validation_error" in str(err)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def test_public_exports():
    import statewave
    assert hasattr(statewave, "StatewaveClient")
    assert hasattr(statewave, "AsyncStatewaveClient")
    assert hasattr(statewave, "StatewaveAPIError")
    assert hasattr(statewave, "StatewaveConnectionError")
    assert hasattr(statewave, "__version__")
    assert isinstance(statewave.__version__, str)
    assert len(statewave.__version__) > 0
