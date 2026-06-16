"""Tests for per-call timeout override and asyncio.CancelledError propagation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from statewave import AsyncStatewaveClient, StatewaveClient


def _mock_response(status: int, *, json_body: dict | None = None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.is_success = 200 <= status < 300
    resp.headers = {}
    resp.reason_phrase = "OK" if resp.is_success else "Error"
    resp.json.return_value = json_body or {
        "id": "ep-1", "subject_id": "s1", "source": "t", "type": "t",
        "payload": {}, "metadata": {}, "provenance": {}, "created_at": "2026-01-01T00:00:00Z",
    }
    return resp


class TestSyncPerCallTimeout:
    def test_timeout_passed_to_httpx(self):
        """Per-call timeout is forwarded to httpx as a request kwarg."""
        client = StatewaveClient()
        resp = _mock_response(200)

        with patch.object(client._http, "request", return_value=resp) as mock_req:
            from statewave.models import Episode
            with patch("statewave.models.Episode.model_validate", return_value=MagicMock()):
                client._request("POST", "/v1/episodes", model=Episode, timeout=5.0)

        _args, kwargs = mock_req.call_args
        assert kwargs.get("timeout") == 5.0

    def test_no_timeout_kwarg_when_none(self):
        """When timeout=None, httpx is not given an explicit timeout kwarg."""
        client = StatewaveClient()
        resp = _mock_response(200)

        with patch.object(client._http, "request", return_value=resp) as mock_req:
            from statewave.models import Episode
            with patch("statewave.models.Episode.model_validate", return_value=MagicMock()):
                client._request("POST", "/v1/episodes", model=Episode)

        _args, kwargs = mock_req.call_args
        assert "timeout" not in kwargs

    def test_public_method_passes_timeout(self):
        """get_context() accepts and forwards timeout to _request."""
        client = StatewaveClient()
        resp = _mock_response(200, json_body={
            "assembled_context": "ctx", "items": [], "token_count": 0,
            "subject_id": "s1", "task": "t",
        })

        with patch.object(client._http, "request", return_value=resp) as mock_req:
            with patch("statewave.models.ContextBundle.model_validate", return_value=MagicMock()):
                client.get_context("s1", "task", timeout=3.0)

        _args, kwargs = mock_req.call_args
        assert kwargs.get("timeout") == 3.0

    def test_keyboard_interrupt_not_retried(self):
        """KeyboardInterrupt propagates immediately without retry."""
        from statewave import RetryConfig
        client = StatewaveClient(retry=RetryConfig(max_retries=3, backoff_base=0.0, jitter=False))

        with patch.object(client._http, "request", side_effect=KeyboardInterrupt):
            from statewave.models import Episode
            with pytest.raises(KeyboardInterrupt):
                client._request("POST", "/v1/episodes", model=Episode)

    def test_compile_memories_wait_request_timeout(self):
        """compile_memories_wait() passes request_timeout to each poll."""
        client = StatewaveClient()
        job_pending = MagicMock()
        job_pending.job_id = "job-1"
        job_pending.status = "pending"
        job_done = MagicMock()
        job_done.job_id = "job-1"
        job_done.status = "completed"

        with patch.object(client, "compile_memories_async", return_value=job_pending) as mock_submit:
            with patch.object(client, "get_compile_status", return_value=job_done) as mock_poll:
                with patch("time.sleep"):
                    client.compile_memories_wait("s1", request_timeout=2.0)

        mock_submit.assert_called_once_with("s1", timeout=2.0)
        mock_poll.assert_called_once_with("job-1", timeout=2.0)


class TestAsyncPerCallTimeout:
    @pytest.mark.asyncio
    async def test_timeout_passed_to_httpx(self):
        """Async per-call timeout is forwarded to httpx."""
        client = AsyncStatewaveClient()
        resp = _mock_response(200)

        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=resp) as mock_req:
            from statewave.models import Episode
            with patch("statewave.models.Episode.model_validate", return_value=MagicMock()):
                await client._request("POST", "/v1/episodes", model=Episode, timeout=7.0)

        _args, kwargs = mock_req.call_args
        assert kwargs.get("timeout") == 7.0

    @pytest.mark.asyncio
    async def test_no_timeout_kwarg_when_none(self):
        """When timeout=None, async httpx is not given an explicit timeout kwarg."""
        client = AsyncStatewaveClient()
        resp = _mock_response(200)

        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=resp) as mock_req:
            from statewave.models import Episode
            with patch("statewave.models.Episode.model_validate", return_value=MagicMock()):
                await client._request("POST", "/v1/episodes", model=Episode)

        _args, kwargs = mock_req.call_args
        assert "timeout" not in kwargs

    @pytest.mark.asyncio
    async def test_cancelled_error_not_retried(self):
        """asyncio.CancelledError propagates immediately without retry."""
        from statewave import RetryConfig
        client = AsyncStatewaveClient(
            retry=RetryConfig(max_retries=3, backoff_base=0.0, jitter=False),
        )

        with patch.object(
            client._http, "request",
            new_callable=AsyncMock, side_effect=asyncio.CancelledError,
        ):
            from statewave.models import Episode
            with pytest.raises(asyncio.CancelledError):
                await client._request("POST", "/v1/episodes", model=Episode)

    @pytest.mark.asyncio
    async def test_cancelled_error_not_swallowed_on_retry_sleep(self):
        """CancelledError raised during retry sleep propagates correctly."""
        from statewave import RetryConfig
        client = AsyncStatewaveClient(
            retry=RetryConfig(max_retries=3, backoff_base=0.01, jitter=False),
        )
        resp_503 = _mock_response(503, json_body={"error": {"code": "unavailable", "message": "down"}})

        async def raise_on_second_sleep(*_a, **_kw):
            raise asyncio.CancelledError

        with patch.object(client._http, "request", new_callable=AsyncMock, return_value=resp_503):
            with patch("asyncio.sleep", side_effect=raise_on_second_sleep):
                from statewave.models import Episode
                with pytest.raises(asyncio.CancelledError):
                    await client._request("POST", "/v1/episodes", model=Episode)

    @pytest.mark.asyncio
    async def test_compile_memories_wait_request_timeout(self):
        """async compile_memories_wait() passes request_timeout to each poll."""
        client = AsyncStatewaveClient()
        job_pending = MagicMock()
        job_pending.job_id = "job-1"
        job_pending.status = "pending"
        job_done = MagicMock()
        job_done.job_id = "job-1"
        job_done.status = "completed"

        with patch.object(
            client, "compile_memories_async",
            new_callable=AsyncMock, return_value=job_pending,
        ) as mock_submit:
            with patch.object(
                client, "get_compile_status",
                new_callable=AsyncMock, return_value=job_done,
            ) as mock_poll:
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await client.compile_memories_wait("s1", request_timeout=2.0)

        mock_submit.assert_called_once_with("s1", timeout=2.0)
        mock_poll.assert_called_once_with("job-1", timeout=2.0)
