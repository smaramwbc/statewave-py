"""Tests for the ``get_timeline`` SDK surface.

``GET /v1/timeline`` orders ascending and caps each collection, so a caller
who takes the server's default page gets a subject's OLDEST records. Past the
cap, recent history was simply unreachable: the SDK sent ``subject_id`` and
nothing else, with no parameter to ask for the other end.

Same class of mismatch as [statewave#174](https://github.com/smaramwbc/statewave/issues/174)
— the REST contract could express something the SDK signature could not.

Server side: [statewave#362](https://github.com/smaramwbc/statewave/pull/362)
(``limit``/``offset`` and the has-more flags) and
[statewave#363](https://github.com/smaramwbc/statewave/pull/363)
(``newest_first``).
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


# A minimal server-shaped timeline. Empty collections keep these tests about
# the request the SDK sends and the response fields it surfaces.
_TIMELINE_RESPONSE = {
    "subject_id": "subj-1",
    "episodes": [],
    "memories": [],
    "episodes_has_more": True,
    "memories_has_more": False,
}

# What a server that predates the pagination work answers.
_TIMELINE_RESPONSE_LEGACY = {
    "subject_id": "subj-1",
    "episodes": [],
    "memories": [],
}


# ---------------------------------------------------------------------------
# Sync client — the request that goes out
# ---------------------------------------------------------------------------


def test_get_timeline_sends_only_subject_id_by_default():
    """Wire shape must be unchanged when no pagination is asked for, so the
    call keeps working against a server that would reject unknown params."""
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, _TIMELINE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        client.get_timeline("subj-1")

    method, path = mock_req.call_args.args
    assert method == "GET"
    assert path == "/v1/timeline"
    assert mock_req.call_args.kwargs["params"] == {"subject_id": "subj-1"}


def test_get_timeline_forwards_pagination_params():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, _TIMELINE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        client.get_timeline("subj-1", limit=20, offset=5, newest_first=True)

    params = mock_req.call_args.kwargs["params"]
    assert params == {
        "subject_id": "subj-1",
        "limit": 20,
        "offset": 5,
        "newest_first": "true",
    }


def test_get_timeline_forwards_newest_first_false_explicitly():
    """An explicit ``False`` is a caller stating the direction, not an unset
    value — it must survive rather than being folded into the default."""
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, _TIMELINE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        client.get_timeline("subj-1", newest_first=False)

    assert mock_req.call_args.kwargs["params"]["newest_first"] == "false"


def _capture_url(client: StatewaveClient, **kwargs) -> httpx.URL:
    """Drive a real request through the transport and return the built URL.

    The other tests patch ``_http.request``, which is above the layer that
    renders the query string. These two are about the string that actually
    reaches the server, so they have to go one level lower.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_TIMELINE_RESPONSE)

    client._http._transport = httpx.MockTransport(handler)
    client.get_timeline("subj-1", **kwargs)
    return seen[0].url


def test_get_timeline_bool_reaches_the_wire_as_lowercase_true():
    """A Python ``True`` has to arrive as something the server parses.

    FastAPI would accept ``True`` as well, but the signature takes a bool and
    something has to render it, so pin what the server actually receives.
    """
    url = _capture_url(StatewaveClient(retry=NO_RETRY), limit=20, newest_first=True)
    assert url.query.decode() == "subject_id=subj-1&limit=20&newest_first=true"


def test_get_timeline_encodes_a_subject_id_with_query_characters():
    """A subject id is caller-supplied text; it must not be able to add a
    parameter the caller never asked for."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_TIMELINE_RESPONSE)

    client = StatewaveClient(retry=NO_RETRY)
    client._http._transport = httpx.MockTransport(handler)
    client.get_timeline("tenant a/user&limit=1", limit=20)

    assert dict(seen[0].url.params) == {
        "subject_id": "tenant a/user&limit=1",
        "limit": "20",
    }


# ---------------------------------------------------------------------------
# Sync client — the response that comes back
# ---------------------------------------------------------------------------


def test_get_timeline_surfaces_the_has_more_flags():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, _TIMELINE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        timeline = client.get_timeline("subj-1", limit=1)

    assert timeline.episodes_has_more is True
    assert timeline.memories_has_more is False


def test_get_timeline_leaves_has_more_none_when_the_server_omits_it():
    """``None`` is "this server did not say", which a caller must be able to
    tell apart from ``False``. Defaulting to ``False`` would turn silence into
    a positive claim that the page is complete."""
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, _TIMELINE_RESPONSE_LEGACY))
    with patch.object(client._http, "request", mock_req):
        timeline = client.get_timeline("subj-1")

    assert timeline.episodes_has_more is None
    assert timeline.memories_has_more is None


def test_get_timeline_surfaces_episode_occurred_at():
    """``occurred_at`` is the column the timeline orders by, so a caller who
    asked for the most recent episodes has to be able to see it. The model
    discarded it before this change — pydantic's default ``extra="ignore"``
    drops any field the model does not declare."""
    client = StatewaveClient(retry=NO_RETRY)
    body = {
        "subject_id": "subj-1",
        "episodes": [
            {
                "id": "11111111-1111-4111-8111-111111111111",
                "subject_id": "subj-1",
                "source": "chat",
                "type": "conversation",
                "payload": {"text": "hi"},
                "metadata": {},
                "provenance": {},
                "occurred_at": "2026-01-01T09:00:00Z",
                "created_at": "2026-05-27T12:00:00Z",
            }
        ],
        "memories": [],
    }
    mock_req = MagicMock(return_value=_resp(200, body))
    with patch.object(client._http, "request", mock_req):
        timeline = client.get_timeline("subj-1", newest_first=True)

    episode = timeline.episodes[0]
    assert episode.occurred_at is not None
    assert episode.occurred_at.year == 2026
    assert episode.occurred_at.hour == 9
    # The event time and the ingest time are different things and both survive.
    assert episode.created_at.month == 5


def test_get_timeline_tolerates_an_episode_without_occurred_at():
    """A response that omits the field must still parse rather than raising."""
    client = StatewaveClient(retry=NO_RETRY)
    body = {
        "subject_id": "subj-1",
        "episodes": [
            {
                "id": "11111111-1111-4111-8111-111111111111",
                "subject_id": "subj-1",
                "source": "chat",
                "type": "conversation",
                "payload": {},
                "metadata": {},
                "provenance": {},
                "created_at": "2026-05-27T12:00:00Z",
            }
        ],
        "memories": [],
    }
    mock_req = MagicMock(return_value=_resp(200, body))
    with patch.object(client._http, "request", mock_req):
        timeline = client.get_timeline("subj-1")

    assert timeline.episodes[0].occurred_at is None


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_get_timeline_sends_only_subject_id_by_default():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, _TIMELINE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        await client.get_timeline("subj-1")

    assert mock_req.call_args.kwargs["params"] == {"subject_id": "subj-1"}


@pytest.mark.asyncio
async def test_async_get_timeline_forwards_pagination_params():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, _TIMELINE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        await client.get_timeline("subj-1", limit=20, offset=5, newest_first=True)

    params = mock_req.call_args.kwargs["params"]
    assert params == {
        "subject_id": "subj-1",
        "limit": 20,
        "offset": 5,
        "newest_first": "true",
    }


@pytest.mark.asyncio
async def test_async_get_timeline_surfaces_the_has_more_flags():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, _TIMELINE_RESPONSE))
    with patch.object(client._http, "request", mock_req):
        timeline = await client.get_timeline("subj-1", newest_first=True)

    assert timeline.episodes_has_more is True
    assert timeline.memories_has_more is False


# ---------------------------------------------------------------------------
# Sync / async parity
# ---------------------------------------------------------------------------


def test_sync_and_async_get_timeline_signatures_agree():
    """The two clients are hand-written copies, so a parameter added to one
    and forgotten on the other is the obvious way this drifts."""
    import inspect

    sync_params = inspect.signature(StatewaveClient.get_timeline).parameters
    async_params = inspect.signature(AsyncStatewaveClient.get_timeline).parameters

    assert list(sync_params) == list(async_params)
    for name, sync_param in sync_params.items():
        assert sync_param.kind == async_params[name].kind, name
        assert sync_param.default == async_params[name].default, name
