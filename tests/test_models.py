"""Smoke tests for the SDK models."""

from statewave.models import Episode, Memory


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
        "source_episode_ids": [],
        "metadata": {},
        "status": "active",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }
    mem = Memory.model_validate(data)
    assert mem.kind == "profile_fact"
