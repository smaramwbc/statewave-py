"""Tests for the ``create_episode`` SDK surface.

Closes [statewave#174](https://github.com/smaramwbc/statewave/issues/174) —
the server has accepted ``session_id`` on ``POST /v1/episodes`` since the
session-aware-ranking work, but the SDK signature was missing the kwarg.
v0.9.4 launch-readiness picked this up as a visible REST-contract / SDK-
signature mismatch worth closing before v1.0.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from statewave import (
    NO_RETRY,
    AsyncStatewaveClient,
    StatewaveClient,
)


def _resp(status: int, body):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.is_success = 200 <= status < 300
    resp.headers = {}
    resp.reason_phrase = "Error"
    resp.json.return_value = body
    return resp


# A response that satisfies the ``Episode`` Pydantic model — server-emitted
# shape, snake_case, no ``session_id`` field (the server response model does
# not echo session_id today; the kwarg is write-only attribution).
_EPISODE_RESPONSE = {
    "id": "11111111-1111-4111-8111-111111111111",
    "subject_id": "subj-1",
    "source": "chat",
    "type": "conversation",
    "payload": {"text": "hi"},
    "metadata": {},
    "provenance": {},
    "created_at": "2026-05-27T12:00:00Z",
}


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------


def test_create_episode_omits_session_id_when_not_passed():
    """Wire shape must be byte-for-byte unchanged when callers don't pass
    session_id — guard against accidentally always sending ``"session_id":
    null`` and breaking pre-v0.9 servers that didn't accept the field."""
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, _EPISODE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        client.create_episode(
            subject_id="subj-1",
            source="chat",
            type="conversation",
            payload={"text": "hi"},
        )

    method, path = mock_req.call_args.args
    assert method == "POST"
    assert path == "/v1/episodes"
    body = mock_req.call_args.kwargs["json"]
    assert "session_id" not in body
    # Sanity: existing fields still wired correctly.
    assert body["subject_id"] == "subj-1"
    assert body["source"] == "chat"
    assert body["type"] == "conversation"
    assert body["payload"] == {"text": "hi"}


def test_create_episode_forwards_session_id():
    """When the caller passes session_id, it appears in the request body
    exactly once, with the verbatim value."""
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, _EPISODE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        client.create_episode(
            subject_id="subj-1",
            source="chat",
            type="conversation",
            payload={"text": "hi"},
            session_id="sess-abc-123",
        )

    body = mock_req.call_args.kwargs["json"]
    assert body["session_id"] == "sess-abc-123"


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_create_episode_omits_session_id_when_not_passed():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, _EPISODE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        await client.create_episode(
            subject_id="subj-1",
            source="chat",
            type="conversation",
            payload={"text": "hi"},
        )

    body = mock_req.call_args.kwargs["json"]
    assert "session_id" not in body


@pytest.mark.asyncio
async def test_async_create_episode_forwards_session_id():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, _EPISODE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        await client.create_episode(
            subject_id="subj-1",
            source="chat",
            type="conversation",
            payload={"text": "hi"},
            session_id="sess-xyz-999",
        )

    body = mock_req.call_args.kwargs["json"]
    assert body["session_id"] == "sess-xyz-999"


# ---------------------------------------------------------------------------
# idempotency_key forwarding
# ---------------------------------------------------------------------------


def test_create_episode_forwards_idempotency_key():
    """idempotency_key is forwarded verbatim so re-ingest de-dups server-side."""
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, _EPISODE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        client.create_episode(
            subject_id="subj-1",
            source="git",
            type="git.commit",
            payload={"text": "hi"},
            idempotency_key="git:commit:abc",
        )
    body = mock_req.call_args.kwargs["json"]
    assert body["idempotency_key"] == "git:commit:abc"


def test_create_episode_omits_idempotency_key_when_not_passed():
    """Wire shape stays unchanged when the caller doesn't pass a key."""
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, _EPISODE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        client.create_episode(
            subject_id="subj-1", source="chat", type="conversation", payload={"text": "hi"}
        )
    body = mock_req.call_args.kwargs["json"]
    assert "idempotency_key" not in body
