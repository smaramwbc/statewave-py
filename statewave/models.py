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
    sensitivity_labels: list[str] = Field(
        default_factory=list,
        description="Per-memory capability tags consumed by the policy layer (#50).",
    )
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
    receipt_id: str | None = None
    receipt_emitted: bool = False


class Receipt(BaseModel):
    """State-assembly receipt — immutable audit artifact of a single
    assembly call. See docs/state-assembly-receipts.md in the server
    repository for the full schema and emission policy."""

    receipt_id: str
    parent_receipt_id: str | None = None
    mode: str
    query_id: str | None = None
    task_id: str | None = None
    tenant_id: str | None = None
    subject_id: str
    task: str
    as_of: str
    created_at: str
    selected_entries: list[dict[str, Any]] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    region: str | None = None
    receipt_signature: str | None = None


class ReceiptList(BaseModel):
    """Paged list of receipts. `next_cursor` is None when there are no
    further results."""

    receipts: list[Receipt] = Field(default_factory=list)
    next_cursor: str | None = None


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


class SubjectSummary(BaseModel):
    subject_id: str
    episode_count: int
    memory_count: int


class ListSubjectsResult(BaseModel):
    subjects: list[SubjectSummary]
    total: int


class CompileJob(BaseModel):
    """Status of an async compile job."""

    job_id: str
    status: str  # pending, running, completed, failed
    subject_id: str
    memories_created: int = 0
    memories: list[Memory] = Field(default_factory=list)
    error: str | None = None
