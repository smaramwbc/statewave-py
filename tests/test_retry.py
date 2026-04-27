"""Tests for retry/backoff behavior."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from statewave import StatewaveClient, RetryConfig, NO_RETRY
from statewave.exceptions import StatewaveAPIError


def _mock_response(status: int, *, headers: dict | None = None, json_body: dict | None = None):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.is_success = 200 <= status < 300
    resp.headers = headers or {}
    resp.reason_phrase = "Error"
    resp.json.return_value = json_body or {"id": "test-123", "subject_id": "s1", "source": "t", "type": "t", "payload": {}, "metadata": {}, "provenance": {}, "created_at": "2026-01-01T00:00:00Z"}
    return resp


class TestRetryConfig:
    def test_default_config(self):
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.backoff_base == 0.5
        assert 429 in cfg.retry_on_status
        assert 503 in cfg.retry_on_status

    def test_delay_exponential(self):
        cfg = RetryConfig(jitter=False)
        assert cfg.delay_for_attempt(0) == 0.5
        assert cfg.delay_for_attempt(1) == 1.0
        assert cfg.delay_for_attempt(2) == 2.0

    def test_delay_respects_max(self):
        cfg = RetryConfig(jitter=False, backoff_max=2.0)
        assert cfg.delay_for_attempt(5) == 2.0

    def test_delay_respects_retry_after(self):
        cfg = RetryConfig(jitter=False)
        assert cfg.delay_for_attempt(0, retry_after=5.0) == 5.0

    def test_no_retry_config(self):
        assert NO_RETRY.max_retries == 0


class TestSyncRetry:
    def test_retries_on_429(self):
        """Client retries on 429 and succeeds."""
        client = StatewaveClient(retry=RetryConfig(max_retries=2, backoff_base=0.01, jitter=False))
        resp_429 = _mock_response(429)
        resp_200 = _mock_response(200)

        with patch.object(client._http, "request", side_effect=[resp_429, resp_200]):
            from statewave.models import Episode
            with patch("statewave.models.Episode.model_validate", return_value=MagicMock()):
                result = client._request("POST", "/v1/episodes", model=Episode)
                assert result is not None

    def test_retries_on_503(self):
        """Client retries on 503."""
        client = StatewaveClient(retry=RetryConfig(max_retries=1, backoff_base=0.01, jitter=False))
        resp_503 = _mock_response(503)
        resp_200 = _mock_response(200)

        with patch.object(client._http, "request", side_effect=[resp_503, resp_200]):
            from statewave.models import Episode
            with patch("statewave.models.Episode.model_validate", return_value=MagicMock()):
                result = client._request("POST", "/v1/episodes", model=Episode)
                assert result is not None

    def test_no_retry_on_400(self):
        """Client does NOT retry on 400."""
        client = StatewaveClient(retry=RetryConfig(max_retries=3, backoff_base=0.01))
        resp_400 = _mock_response(400, json_body={"error": {"code": "validation", "message": "bad"}})

        with patch.object(client._http, "request", return_value=resp_400):
            with pytest.raises(StatewaveAPIError) as exc_info:
                from statewave.models import Episode
                client._request("POST", "/v1/episodes", model=Episode)
            assert exc_info.value.status_code == 400

    def test_no_retry_on_401(self):
        """Client does NOT retry on 401."""
        client = StatewaveClient(retry=RetryConfig(max_retries=3, backoff_base=0.01))
        resp_401 = _mock_response(401, json_body={"error": {"code": "unauthorized", "message": "bad key"}})

        with patch.object(client._http, "request", return_value=resp_401):
            with pytest.raises(StatewaveAPIError) as exc_info:
                from statewave.models import Episode
                client._request("POST", "/v1/episodes", model=Episode)
            assert exc_info.value.status_code == 401

    def test_retries_on_connection_error(self):
        """Client retries on connection failures."""
        client = StatewaveClient(retry=RetryConfig(max_retries=2, backoff_base=0.01, jitter=False))
        resp_200 = _mock_response(200)

        with patch.object(client._http, "request", side_effect=[httpx.ConnectError("down"), resp_200]):
            from statewave.models import Episode
            with patch("statewave.models.Episode.model_validate", return_value=MagicMock()):
                result = client._request("POST", "/v1/episodes", model=Episode)
                assert result is not None

    def test_raises_after_max_retries_exhausted(self):
        """Client raises after all retries fail."""
        client = StatewaveClient(retry=RetryConfig(max_retries=2, backoff_base=0.01, jitter=False))
        resp_503 = _mock_response(503, json_body={"error": {"code": "unavailable", "message": "down"}})

        with patch.object(client._http, "request", return_value=resp_503):
            with pytest.raises(StatewaveAPIError) as exc_info:
                from statewave.models import Episode
                client._request("POST", "/v1/episodes", model=Episode)
            assert exc_info.value.status_code == 503

    def test_no_retry_disabled(self):
        """NO_RETRY config means zero retries."""
        client = StatewaveClient(retry=NO_RETRY)
        resp_503 = _mock_response(503, json_body={"error": {"code": "unavailable", "message": "down"}})

        with patch.object(client._http, "request", return_value=resp_503) as mock_req:
            with pytest.raises(StatewaveAPIError):
                from statewave.models import Episode
                client._request("POST", "/v1/episodes", model=Episode)
            assert mock_req.call_count == 1

    def test_respects_retry_after_header(self):
        """Client respects Retry-After header."""
        client = StatewaveClient(retry=RetryConfig(max_retries=1, backoff_base=0.01, jitter=False))
        resp_429 = _mock_response(429, headers={"retry-after": "0.02"})
        resp_200 = _mock_response(200)

        with patch.object(client._http, "request", side_effect=[resp_429, resp_200]):
            from statewave.models import Episode
            with patch("statewave.models.Episode.model_validate", return_value=MagicMock()):
                start = time.time()
                client._request("POST", "/v1/episodes", model=Episode)
                elapsed = time.time() - start
                assert elapsed >= 0.02


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_retries_on_429(self):
        """Async client retries on 429."""
        from statewave import AsyncStatewaveClient
        client = AsyncStatewaveClient(retry=RetryConfig(max_retries=1, backoff_base=0.01, jitter=False))
        resp_429 = _mock_response(429)
        resp_200 = _mock_response(200)

        with patch.object(client._http, "request", side_effect=[resp_429, resp_200]):
            from statewave.models import Episode
            with patch("statewave.models.Episode.model_validate", return_value=MagicMock()):
                result = await client._request("POST", "/v1/episodes", model=Episode)
                assert result is not None

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        """Async client raises after retries exhausted."""
        from statewave import AsyncStatewaveClient
        client = AsyncStatewaveClient(retry=RetryConfig(max_retries=1, backoff_base=0.01, jitter=False))
        resp_500 = _mock_response(500, json_body={"error": {"code": "internal", "message": "oops"}})

        with patch.object(client._http, "request", return_value=resp_500):
            with pytest.raises(StatewaveAPIError) as exc_info:
                from statewave.models import Episode
                await client._request("POST", "/v1/episodes", model=Episode)
            assert exc_info.value.status_code == 500
