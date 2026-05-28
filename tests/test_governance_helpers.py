"""Tests for the v0.9 governance SDK helpers — suggested-label review (#176).

Wire payloads mirror the admin endpoints
``GET /admin/memories/with-suggested-labels`` and
``POST /admin/memories/{id}/promote-labels`` exactly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from statewave import (
    NO_RETRY,
    AsyncStatewaveClient,
    PromoteLabelsResult,
    StatewaveClient,
    SuggestedLabelsList,
)


def _resp(status: int, body):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.is_success = 200 <= status < 300
    resp.headers = {}
    resp.reason_phrase = "Error"
    resp.json.return_value = body
    return resp


LIST_BODY = {
    "memories": [
        {
            "id": "m1",
            "subject_id": "user:42",
            "tenant_id": None,
            "kind": "profile_fact",
            "content": "card on file",
            "summary": "payment card on file",
            "suggested_labels": ["financial.card"],
            "sensitivity_labels": [],
            "created_at": "2026-05-20T00:00:00Z",
        }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0,
    "catalogue": [{"label": "financial.card", "detector": "luhn"}],
}

PROMOTE_BODY = {
    "memory_id": "m1",
    "promoted": ["financial.card"],
    "sensitivity_labels": ["financial.card"],
    "suggested_labels": [],
}


def test_list_suggested_labels_sync():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, LIST_BODY))
    with patch.object(client._http, "request", mock_req):
        result = client.list_suggested_labels(label="financial.card")

    assert isinstance(result, SuggestedLabelsList)
    assert result.total == 1
    assert result.memories[0].suggested_labels == ["financial.card"]
    method, path = mock_req.call_args.args
    assert method == "GET"
    assert path == "/admin/memories/with-suggested-labels"
    assert mock_req.call_args.kwargs["params"]["label"] == "financial.card"


def test_promote_suggested_labels_sync():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, PROMOTE_BODY))
    with patch.object(client._http, "request", mock_req):
        result = client.promote_suggested_labels("m1", ["financial.card"])

    assert isinstance(result, PromoteLabelsResult)
    assert result.promoted == ["financial.card"]
    assert result.sensitivity_labels == ["financial.card"]
    assert result.suggested_labels == []
    method, path = mock_req.call_args.args
    assert method == "POST"
    assert path == "/admin/memories/m1/promote-labels"
    assert mock_req.call_args.kwargs["json"] == {"labels": ["financial.card"]}


@pytest.mark.asyncio
async def test_governance_helpers_async():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    with patch.object(client._http, "request", AsyncMock(return_value=_resp(200, LIST_BODY))):
        listed = await client.list_suggested_labels()
    assert listed.memories[0].id == "m1"

    with patch.object(client._http, "request", AsyncMock(return_value=_resp(200, PROMOTE_BODY))):
        promoted = await client.promote_suggested_labels("m1", ["financial.card"])
    assert promoted.promoted == ["financial.card"]
