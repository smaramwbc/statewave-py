"""Pydantic models matching the Statewave API contract."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Episode(BaseModel):
    id: uuid.UUID
    subject_id: str
    source: str
    type: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Memory(BaseModel):
    id: uuid.UUID
    subject_id: str
    kind: str
    content: str
    summary: str = ""
    confidence: float = 1.0
    valid_from: datetime
    valid_to: datetime | None = None
    source_episode_ids: list[uuid.UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    created_at: datetime
    updated_at: datetime


class CompileResult(BaseModel):
    subject_id: str
    memories_created: int
    memories: list[Memory]


class SearchResult(BaseModel):
    memories: list[Memory]


class ContextBundle(BaseModel):
    subject_id: str
    task: str
    facts: list[Memory] = Field(default_factory=list)
    episodes: list[Episode] = Field(default_factory=list)
    procedures: list[Memory] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    assembled_context: str = ""
    token_estimate: int = 0


class Timeline(BaseModel):
    subject_id: str
    episodes: list[Episode]
    memories: list[Memory]


class DeleteResult(BaseModel):
    subject_id: str
    episodes_deleted: int
    memories_deleted: int


class BatchCreateResult(BaseModel):
    episodes_created: int
    episodes: list[Episode]
