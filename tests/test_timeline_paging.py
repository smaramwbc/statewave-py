"""get_timeline / list_resolutions paging params are sent only when given."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from statewave import NO_RETRY, AsyncStatewaveClient, StatewaveClient, Timeline
TIMELINE_BODY = {"subject_id": "u1", "episodes": [], "memories": []}
PAGED_BODY = {**TIMELINE_BODY, "episodes_has_more": True, "memories_has_more": False}


def _resp(status: int, body):
    """Build a mock httpx.Response carrying ``body`` as its JSON payload."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.is_success = 200 <= status < 300
    resp.headers = {}
    resp.reason_phrase = "Error"
    resp.json.return_value = body
    return resp


def test_get_timeline_default_sends_only_subject_id():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, TIMELINE_BODY))
    with patch.object(client._http, "request", mock_req):
        t = client.get_timeline("u1")
    assert isinstance(t, Timeline)
    assert t.episodes_has_more is None and t.memories_has_more is None
    assert mock_req.call_args.kwargs["params"] == {"subject_id": "u1"}


def test_get_timeline_sends_paging_params_and_reads_has_more():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, PAGED_BODY))
    with patch.object(client._http, "request", mock_req):
        t = client.get_timeline("u1", limit=20, offset=40, newest_first=True)
    assert t.episodes_has_more is True and t.memories_has_more is False
    assert mock_req.call_args.kwargs["params"] == {
        "subject_id": "u1",
        "limit": 20,
        "offset": 40,
        "newest_first": "true",
    }


def test_get_timeline_newest_first_false_is_explicit():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, TIMELINE_BODY))
    with patch.object(client._http, "request", mock_req):
        client.get_timeline("u1", newest_first=False)
    assert mock_req.call_args.kwargs["params"] == {"subject_id": "u1", "newest_first": "false"}


def test_list_resolutions_sends_limit_and_offset():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, []))
    with patch.object(client._http, "request", mock_req):
        client.list_resolutions("u1", limit=2, offset=4)
    assert mock_req.call_args.kwargs["params"] == {"subject_id": "u1", "limit": 2, "offset": 4}


@pytest.mark.anyio
async def test_get_timeline_async_sends_paging_params():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, PAGED_BODY))
    with patch.object(client._http, "request", mock_req):
        t = await client.get_timeline("u1", limit=5, newest_first=True)
    assert t.episodes_has_more is True
    assert mock_req.call_args.kwargs["params"] == {
        "subject_id": "u1",
        "limit": 5,
        "newest_first": "true",
    }
