"""Tests for the v0.9 receipt-governance SDK helpers — verify + replay.

The wire payloads here mirror the server responses exactly (snake_case,
canonical ``error.code = unreplayable.<reason>`` envelope on 422).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from statewave import (
    NO_RETRY,
    UNREPLAYABLE_REASONS,
    AsyncStatewaveClient,
    ReceiptReplayResult,
    ReceiptVerifyResult,
    StatewaveAPIError,
    StatewaveClient,
    StatewaveUnreplayableError,
)


def _resp(status: int, body):
    """Build a mock httpx.Response carrying ``body`` as its JSON payload."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.is_success = 200 <= status < 300
    resp.headers = {}
    resp.reason_phrase = "Error"
    resp.json.return_value = body
    return resp


# ---------------------------------------------------------------------------
# Representative wire payloads — match server response shapes exactly
# ---------------------------------------------------------------------------

VERIFY_OK_BODY = {
    "valid": True,
    "key_id": "key-2026-01",
    "algorithm": "hmac-sha256-canonical-v1",
    "reason": "ok",
}

VERIFY_NO_SIGNATURE_BODY = {
    "valid": None,
    "key_id": None,
    "algorithm": None,
    "reason": "no_signature",
}

VERIFY_KEY_UNAVAILABLE_BODY = {
    "valid": None,
    "key_id": "key-2025-12",
    "algorithm": "hmac-sha256-canonical-v1",
    "reason": "key_unavailable",
}

VERIFY_MISMATCH_BODY = {
    "valid": False,
    "key_id": "key-2026-01",
    "algorithm": "hmac-sha256-canonical-v1",
    "reason": "signature_mismatch",
}

REPLAY_OK_BODY = {
    "original_receipt_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
    "replay_receipt_id": "01ARZ3NDEKTSV4RRFFQ69G5FAW",
    "diff": {
        "context_hash": {
            "original": "a" * 64,
            "replay": "b" * 64,
            "changed": True,
        },
        "selected_entries": {
            "added": [
                {
                    "type": "memory",
                    "memory_id": "00000000-0000-0000-0000-000000000002",
                    "rank": 1,
                },
            ],
            "removed": [],
            "common": 3,
        },
        "filters_applied": {"added": [], "removed": []},
    },
}

REPLAY_WRITE_FAILED_BODY = {
    # The replay-receipt write itself failed (rare, fail-open). The
    # diff envelope is still authoritative; replay_receipt_id is None
    # and the original entries appear under `removed`.
    "original_receipt_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
    "replay_receipt_id": None,
    "diff": {
        "context_hash": {"original": "a" * 64, "replay": None, "changed": True},
        "selected_entries": {
            "added": [],
            "removed": [{"type": "memory", "memory_id": "m1", "rank": 1}],
            "common": 0,
        },
        "filters_applied": {"added": [], "removed": []},
    },
}


def _unreplayable_body(reason: str) -> dict:
    """Build the standard error envelope the server emits on 422
    unreplayable.<reason>."""
    return {
        "error": {
            "code": f"unreplayable.{reason}",
            "message": f"receipt is unreplayable: {reason}",
            "details": None,
            "request_id": "test-req-id",
        }
    }


# ---------------------------------------------------------------------------
# Sync: verify_receipt
# ---------------------------------------------------------------------------


def test_verify_receipt_ok():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, VERIFY_OK_BODY))
    with patch.object(client._http, "request", mock_req):
        result = client.verify_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")

    assert isinstance(result, ReceiptVerifyResult)
    assert result.valid is True
    assert result.reason == "ok"
    assert result.key_id == "key-2026-01"
    assert result.algorithm == "hmac-sha256-canonical-v1"

    method, path = mock_req.call_args.args
    assert method == "GET"
    assert path == "/v1/receipts/01ARZ3NDEKTSV4RRFFQ69G5FAV/verify"


def test_verify_receipt_no_signature_returns_none_valid():
    """Pre-v0.9 receipt path — `valid` is None, not False, and reason
    is `no_signature`. This is the most common case in production."""
    client = StatewaveClient(retry=NO_RETRY)
    with patch.object(client._http, "request", MagicMock(return_value=_resp(200, VERIFY_NO_SIGNATURE_BODY))):
        result = client.verify_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result.valid is None
    assert result.reason == "no_signature"
    assert result.key_id is None
    assert result.algorithm is None


def test_verify_receipt_key_unavailable():
    """Key rotated out of operator config. `valid` is None (not False),
    `reason == "key_unavailable"`, and `key_id` is still echoed so an
    auditor can correlate against the old key registry."""
    client = StatewaveClient(retry=NO_RETRY)
    with patch.object(client._http, "request", MagicMock(return_value=_resp(200, VERIFY_KEY_UNAVAILABLE_BODY))):
        result = client.verify_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result.valid is None
    assert result.reason == "key_unavailable"
    assert result.key_id == "key-2025-12"


def test_verify_receipt_signature_mismatch():
    """Math failed — body was tampered with. `valid` is False, not None."""
    client = StatewaveClient(retry=NO_RETRY)
    with patch.object(client._http, "request", MagicMock(return_value=_resp(200, VERIFY_MISMATCH_BODY))):
        result = client.verify_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result.valid is False
    assert result.reason == "signature_mismatch"


# ---------------------------------------------------------------------------
# Sync: replay_receipt — happy path + each refusal code
# ---------------------------------------------------------------------------


def test_replay_receipt_ok():
    client = StatewaveClient(retry=NO_RETRY)
    mock_req = MagicMock(return_value=_resp(200, REPLAY_OK_BODY))
    with patch.object(client._http, "request", mock_req):
        result = client.replay_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")

    assert isinstance(result, ReceiptReplayResult)
    assert result.original_receipt_id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    assert result.replay_receipt_id == "01ARZ3NDEKTSV4RRFFQ69G5FAW"
    assert result.diff.context_hash["changed"] is True
    assert result.diff.selected_entries["added"][0]["memory_id"] == "00000000-0000-0000-0000-000000000002"
    assert result.diff.selected_entries["common"] == 3

    method, path = mock_req.call_args.args
    assert method == "POST"
    assert path == "/v1/receipts/01ARZ3NDEKTSV4RRFFQ69G5FAV/replay"


def test_replay_receipt_write_failed_path():
    """`replay_receipt_id is None` is a valid response — the diff is
    still authoritative."""
    client = StatewaveClient(retry=NO_RETRY)
    with patch.object(client._http, "request", MagicMock(return_value=_resp(200, REPLAY_WRITE_FAILED_BODY))):
        result = client.replay_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result.replay_receipt_id is None
    assert result.diff.context_hash["original"] == "a" * 64
    assert result.diff.context_hash["replay"] is None
    assert len(result.diff.selected_entries["removed"]) == 1


@pytest.mark.parametrize("reason", sorted(UNREPLAYABLE_REASONS))
def test_replay_receipt_refusal_codes_raise_unreplayable_error(reason):
    """Every documented refusal code on the server side must map to
    a typed StatewaveUnreplayableError on the client side. This is
    the load-bearing test for #169's typed-exception contract."""
    client = StatewaveClient(retry=NO_RETRY)
    body = _unreplayable_body(reason)
    with patch.object(client._http, "request", MagicMock(return_value=_resp(422, body))):
        with pytest.raises(StatewaveUnreplayableError) as exc_info:
            client.replay_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")

    err = exc_info.value
    assert err.reason == reason
    assert err.code == f"unreplayable.{reason}"
    assert err.status_code == 422
    assert err.request_id == "test-req-id"
    # Subclass of StatewaveAPIError so generic handlers still catch it.
    assert isinstance(err, StatewaveAPIError)


def test_replay_receipt_unknown_unreplayable_reason_falls_back_to_api_error():
    """A future server release might add a new refusal code we haven't
    learned yet. The SDK should keep the body parseable and surface
    it as a generic StatewaveAPIError rather than crashing."""
    client = StatewaveClient(retry=NO_RETRY)
    body = {
        "error": {
            "code": "unreplayable.brand_new_reason",
            "message": "future reason",
            "request_id": "x",
        }
    }
    with patch.object(client._http, "request", MagicMock(return_value=_resp(422, body))):
        with pytest.raises(StatewaveAPIError) as exc_info:
            client.replay_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    err = exc_info.value
    # Not promoted to StatewaveUnreplayableError because the reason
    # is not in the known set.
    assert not isinstance(err, StatewaveUnreplayableError)
    assert err.code == "unreplayable.brand_new_reason"


def test_replay_receipt_other_4xx_still_raises_generic_api_error():
    """A 404 (receipt not found / cross-tenant) is not an
    unreplayable refusal — same generic StatewaveAPIError as today."""
    client = StatewaveClient(retry=NO_RETRY)
    body = {"error": {"code": "not_found", "message": "receipt not found"}}
    with patch.object(client._http, "request", MagicMock(return_value=_resp(404, body))):
        with pytest.raises(StatewaveAPIError) as exc_info:
            client.replay_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    err = exc_info.value
    assert not isinstance(err, StatewaveUnreplayableError)
    assert err.status_code == 404
    assert err.code == "not_found"


# ---------------------------------------------------------------------------
# Async: same happy + refusal paths
# ---------------------------------------------------------------------------


async def test_async_verify_receipt_ok():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, VERIFY_OK_BODY))
    with patch.object(client._http, "request", mock_req):
        result = await client.verify_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result.valid is True
    assert result.reason == "ok"


async def test_async_replay_receipt_ok():
    client = AsyncStatewaveClient(retry=NO_RETRY)
    mock_req = AsyncMock(return_value=_resp(200, REPLAY_OK_BODY))
    with patch.object(client._http, "request", mock_req):
        result = await client.replay_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result.replay_receipt_id == "01ARZ3NDEKTSV4RRFFQ69G5FAW"
    method, path = mock_req.call_args.args
    assert method == "POST"
    assert path == "/v1/receipts/01ARZ3NDEKTSV4RRFFQ69G5FAV/replay"


async def test_async_replay_receipt_missing_policy_snapshot_raises_typed_error():
    """Async parity for the pre-v0.9-receipt refusal case — the most
    common one operators will hit."""
    client = AsyncStatewaveClient(retry=NO_RETRY)
    body = _unreplayable_body("missing_policy_snapshot")
    mock_req = AsyncMock(return_value=_resp(422, body))
    with patch.object(client._http, "request", mock_req):
        with pytest.raises(StatewaveUnreplayableError) as exc_info:
            await client.replay_receipt("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert exc_info.value.reason == "missing_policy_snapshot"


# ---------------------------------------------------------------------------
# Receipt model carries the v0.9 governance fields
# ---------------------------------------------------------------------------


def test_receipt_model_accepts_v0_9_governance_fields():
    """The Receipt model must absorb the v0.9 fields without
    config tweaks — otherwise pip-show users of pre-v0.10.1 clients
    against a v0.9 server would silently drop fields."""
    from statewave import Receipt

    body = {
        "receipt_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "mode": "as_of_replay",
        "subject_id": "user-42",
        "task": "replay test",
        "as_of": "2026-05-26T18:00:00+00:00",
        "created_at": "2026-05-26T18:00:00+00:00",
        "selected_entries": [],
        "policy": {},
        "output": {"context_hash": "x" * 64, "context_size_bytes": 0,
                   "canonicalization_version": 1, "token_estimate": 0},
        "region": "eu",
        "receipt_signature": "abc123",
        "receipt_signature_key_id": "key-2026-01",
        "receipt_signature_algorithm": "hmac-sha256-canonical-v1",
        "policy_snapshot": {
            "bundle_hash": "snap-abc",
            "bundle_yaml": "version: 1\nrules: []\n",
            "captured_at": "2026-05-26T17:59:00+00:00",
        },
    }
    r = Receipt.model_validate(body)
    assert r.mode == "as_of_replay"
    assert r.region == "eu"
    assert r.receipt_signature_key_id == "key-2026-01"
    assert r.receipt_signature_algorithm == "hmac-sha256-canonical-v1"
    assert r.policy_snapshot is not None
    assert r.policy_snapshot["bundle_yaml"].startswith("version: 1")


def test_receipt_model_pre_v0_9_compatible():
    """Pre-v0.9 receipts (no signature, no snapshot, no algorithm/key_id)
    must still validate — the new fields are all Optional with a None
    default."""
    from statewave import Receipt

    body = {
        "receipt_id": "01ARZ3NDEKTSV4RRFFQ69G5FAU",
        "mode": "retrieval",
        "subject_id": "user-42",
        "task": "old query",
        "as_of": "2026-05-12T10:00:00+00:00",
        "created_at": "2026-05-12T10:00:00+00:00",
        "selected_entries": [],
        "policy": {},
        "output": {"context_hash": "y" * 64, "context_size_bytes": 0,
                   "canonicalization_version": 1, "token_estimate": 0},
        "region": None,
        "receipt_signature": None,
    }
    r = Receipt.model_validate(body)
    assert r.mode == "retrieval"
    assert r.policy_snapshot is None
    assert r.receipt_signature_key_id is None
