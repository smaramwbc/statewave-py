"""Tests for the support-agent SDK methods (health, SLA, handoff, resolutions)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from statewave import (
    NO_RETRY,
    AsyncStatewaveClient,
    Handoff,
    Health,
    Resolution,
    SLASummary,
    StatewaveClient,
)
from statewave.exceptions import StatewaveAPIError


def _resp(status: int, body):
    """Build a mock httpx.Response carrying ``body`` as its JSON payload."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.is_success = 200 <= status < 300
    resp.headers = {}
    resp.reason_phrase = "Error"
    resp.json.return_value = body
    return resp


# Representative wire payloads — snake_case, exactly as the server emits them.

HEALTH_BODY = {
    "subject_id": "customer:globex",
    "score": 72,
    "state": "watch",
    "factors": [
        {"signal": "sla_resolution_breaches", "impact": -10, "detail": "1 breach"},
    ],
}

SLA_BODY = {
    "subject_id": "u1",
    "total_sessions": 2,
    "resolved_sessions": 1,
    "open_sessions": 1,
    "avg_first_response_seconds": 120.0,
    "avg_resolution_seconds": 3600.0,
    "first_response_breach_count": 0,
    "resolution_breach_count": 1,
    "sessions": [
        {
            "session_id": "s1",
            "status": "resolved",
            "first_message_at": "2026-05-01T00:00:00Z",
            "first_response_at": "2026-05-01T00:02:00Z",
            "resolved_at": "2026-05-01T01:00:00Z",
            "first_response_seconds": 120.0,
            "resolution_seconds": 3600.0,
            "open_duration_seconds": None,
            "first_response_breached": False,
            "resolution_breached": True,
        },
    ],
}

HANDOFF_BODY = {
    "subject_id": "u1",
    "session_id": "sess-1",
    "reason": "escalation",
    "generated_at": "2026-05-21T10:00:00Z",
    "customer_summary": "Enterprise customer",
    "active_issue": "Duplicate charge",
    "attempted_steps": ["checked billing"],
    "key_facts": ["plan: enterprise"],
    "resolution_history": [
        {
            "session_id": "s0",
            "status": "resolved",
            "summary": "refund",
            "resolved_at": "2026-05-01T00:00:00Z",
        },
    ],
    "recent_context": ["asked about refund"],
    "health_score": 60,
    "health_state": "watch",
    "health_factors": [{"signal": "open_sessions", "impact": -5, "detail": "1 open"}],
    "handoff_notes": "# Handoff Brief",
    "token_estimate": 180,
    "provenance": {"fact_ids": ["f1"], "episode_ids": ["e1"]},
    "receipt_id": None,
    "receipt_emitted": False,
}

RESOLUTION_BODY = {
    "id": "00000000-0000-0000-0000-000000000001",
    "subject_id": "u1",
    "session_id": "sess-1",
    "status": "resolved",
    "resolution_summary": "Issued refund",
    "resolved_at": "2026-05-21T10:00:00Z",
    "metadata": {"refund_id": "r-9"},
    "created_at": "2026-05-21T09:00:00Z",
    "updated_at": "2026-05-21T10:00:00Z",
}


# ---------------------------------------------------------------------------
# Model parsing
# ---------------------------------------------------------------------------

def test_health_parse():
    h = Health.model_validate(HEALTH_BODY)
    assert h.score == 72
    assert h.state == "watch"
    assert h.factors[0].signal == "sla_resolution_breaches"
    assert h.factors[0].impact == -10


def test_health_parse_default_empty_factors():
    """Servers without health factors still parse — factors defaults to []."""
    h = Health.model_validate({"subject_id": "u1", "score": 100, "state": "healthy"})
    assert h.factors == []


def test_sla_summary_parse():
    s = SLASummary.model_validate(SLA_BODY)
    assert s.total_sessions == 2
    assert s.resolution_breach_count == 1
    assert len(s.sessions) == 1
    assert s.sessions[0].session_id == "s1"
    assert s.sessions[0].resolution_breached is True
    assert s.sessions[0].open_duration_seconds is None


def test_handoff_parse():
    h = Handoff.model_validate(HANDOFF_BODY)
    assert h.customer_summary == "Enterprise customer"
    assert h.attempted_steps == ["checked billing"]
    assert h.resolution_history[0].session_id == "s0"
    assert h.health_factors[0].signal == "open_sessions"
    assert h.handoff_notes == "# Handoff Brief"
    assert h.provenance["fact_ids"] == ["f1"]
    assert h.receipt_emitted is False


def test_resolution_parse():
    r = Resolution.model_validate(RESOLUTION_BODY)
    assert r.status == "resolved"
    assert r.resolution_summary == "Issued refund"
    assert r.metadata["refund_id"] == "r-9"
    assert r.resolved_at is not None


# ---------------------------------------------------------------------------
# Sync client methods
# ---------------------------------------------------------------------------

def test_get_health_sync():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, HEALTH_BODY))
    with patch.object(client._http, "request", mock_req):
        health = client.get_health("customer:globex")
    assert isinstance(health, Health)
    assert health.score == 72
    method, path = mock_req.call_args.args
    assert method == "GET"
    assert path == "/v1/subjects/customer:globex/health"


def test_get_sla_sync_encodes_thresholds():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, SLA_BODY))
    with patch.object(client._http, "request", mock_req):
        sla = client.get_sla(
            "u1",
            first_response_threshold_minutes=10,
            resolution_threshold_hours=48,
        )
    assert sla.total_sessions == 2
    assert mock_req.call_args.kwargs["params"] == {
        "first_response_threshold_minutes": 10,
        "resolution_threshold_hours": 48,
    }


def test_get_sla_sync_omits_unset_thresholds():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, SLA_BODY))
    with patch.object(client._http, "request", mock_req):
        client.get_sla("u1")
    assert mock_req.call_args.kwargs["params"] == {}


def test_create_handoff_sync():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, HANDOFF_BODY))
    with patch.object(client._http, "request", mock_req):
        handoff = client.create_handoff(
            "u1",
            "sess-1",
            reason="escalation",
            max_tokens=500,
            caller_id="agent-7",
            caller_type="support_agent",
        )
    assert handoff.handoff_notes == "# Handoff Brief"
    method, path = mock_req.call_args.args
    assert (method, path) == ("POST", "/v1/handoff")
    body = mock_req.call_args.kwargs["json"]
    assert body["subject_id"] == "u1"
    assert body["session_id"] == "sess-1"
    assert body["max_tokens"] == 500
    assert body["caller_id"] == "agent-7"
    assert body["caller_type"] == "support_agent"


def test_create_handoff_sync_omits_unset_optionals():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, HANDOFF_BODY))
    with patch.object(client._http, "request", mock_req):
        client.create_handoff("u1", "sess-1")
    assert mock_req.call_args.kwargs["json"] == {
        "subject_id": "u1",
        "session_id": "sess-1",
    }


def test_create_resolution_sync():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, RESOLUTION_BODY))
    with patch.object(client._http, "request", mock_req):
        resolution = client.create_resolution(
            "u1",
            "sess-1",
            status="resolved",
            resolution_summary="Issued refund",
            metadata={"refund_id": "r-9"},
        )
    assert resolution.status == "resolved"
    body = mock_req.call_args.kwargs["json"]
    assert body["status"] == "resolved"
    assert body["resolution_summary"] == "Issued refund"
    assert body["metadata"] == {"refund_id": "r-9"}


def test_create_resolution_sync_defaults_status_open():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, RESOLUTION_BODY))
    with patch.object(client._http, "request", mock_req):
        client.create_resolution("u1", "sess-1")
    assert mock_req.call_args.kwargs["json"] == {
        "subject_id": "u1",
        "session_id": "sess-1",
        "status": "open",
    }


def test_list_resolutions_sync_returns_list():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, [RESOLUTION_BODY, RESOLUTION_BODY]))
    with patch.object(client._http, "request", mock_req):
        resolutions = client.list_resolutions("u1", status="resolved")
    assert isinstance(resolutions, list)
    assert len(resolutions) == 2
    assert all(isinstance(r, Resolution) for r in resolutions)
    assert mock_req.call_args.kwargs["params"] == {
        "subject_id": "u1",
        "status": "resolved",
    }


def test_list_resolutions_sync_empty():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, []))
    with patch.object(client._http, "request", mock_req):
        resolutions = client.list_resolutions("u1")
    assert resolutions == []
    assert mock_req.call_args.kwargs["params"] == {"subject_id": "u1"}


def test_get_health_sync_404_raises():
    client = StatewaveClient(retry=NO_RETRY)
    err = {"error": {"code": "not_found", "message": "unknown subject"}}
    mock_req = MagicMock(return_value=_resp(404, err))
    with patch.object(client._http, "request", mock_req):
        with pytest.raises(StatewaveAPIError) as exc:
            client.get_health("ghost")
    assert exc.value.status_code == 404


def test_create_handoff_sync_401_raises():
    """The caller-identity gate (require_caller_identity) surfaces as a 401."""
    client = StatewaveClient(retry=NO_RETRY)
    err = {"error": {"code": "unauthorized", "message": "caller identity required"}}
    mock_req = MagicMock(return_value=_resp(401, err))
    with patch.object(client._http, "request", mock_req):
        with pytest.raises(StatewaveAPIError) as exc:
            client.create_handoff("u1", "sess-1")
    assert exc.value.status_code == 401
    assert mock_req.call_count == 1  # 401 is not retried


# ---------------------------------------------------------------------------
# Async client methods
# ---------------------------------------------------------------------------

async def test_get_health_async():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, HEALTH_BODY))
    with patch.object(client._http, "request", mock_req):
        health = await client.get_health("u1")
    assert isinstance(health, Health)
    assert health.score == 72


async def test_get_sla_async():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, SLA_BODY))
    with patch.object(client._http, "request", mock_req):
        sla = await client.get_sla("u1", resolution_threshold_hours=12)
    assert sla.resolution_breach_count == 1
    assert mock_req.call_args.kwargs["params"] == {"resolution_threshold_hours": 12}


async def test_create_handoff_async():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, HANDOFF_BODY))
    with patch.object(client._http, "request", mock_req):
        handoff = await client.create_handoff("u1", "sess-1", reason="shift_change")
    assert isinstance(handoff, Handoff)
    assert mock_req.call_args.kwargs["json"]["reason"] == "shift_change"


async def test_create_resolution_async():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, RESOLUTION_BODY))
    with patch.object(client._http, "request", mock_req):
        resolution = await client.create_resolution("u1", "sess-1", status="resolved")
    assert resolution.status == "resolved"


async def test_list_resolutions_async():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, [RESOLUTION_BODY]))
    with patch.object(client._http, "request", mock_req):
        resolutions = await client.list_resolutions("u1")
    assert len(resolutions) == 1
    assert isinstance(resolutions[0], Resolution)


async def test_create_handoff_async_401_raises():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    err = {"error": {"code": "unauthorized", "message": "caller identity required"}}
    mock_req = AsyncMock(return_value=_resp(401, err))
    with patch.object(client._http, "request", mock_req):
        with pytest.raises(StatewaveAPIError) as exc:
            await client.create_handoff("u1", "sess-1")
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def test_support_models_exported():
    import statewave

    for name in (
        "Health",
        "HealthFactor",
        "SLASummary",
        "SessionSLA",
        "Handoff",
        "ResolutionSummaryItem",
        "Resolution",
    ):
        assert hasattr(statewave, name), f"{name} missing from public exports"
