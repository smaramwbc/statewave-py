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
    """``"retrieval"`` for ``/v1/context`` + ``/v1/handoff`` emissions,
    ``"as_of_replay"`` for receipts emitted by
    ``POST /v1/receipts/{id}/replay`` (v0.9+)."""
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
    """Server region the receipt was emitted from (v0.9+ residency).
    ``None`` in single-region deployments."""
    receipt_signature: str | None = None
    """HMAC-SHA256 hex digest over the canonical body (v0.9+ #157).
    ``None`` for pre-v0.9 receipts or tenants without signing
    configured — those verify cleanly as
    ``{valid: None, reason: "no_signature"}``."""
    receipt_signature_key_id: str | None = None
    """Operator key id used to sign (v0.9+). ``None`` when unsigned."""
    receipt_signature_algorithm: str | None = None
    """Algorithm + canonical-form version (e.g.
    ``"hmac-sha256-canonical-v1"``) (v0.9+). ``None`` when unsigned."""
    policy_snapshot: dict[str, Any] | None = None
    """Embedded policy bundle YAML + hash + capture timestamp (v0.9+ #159).
    Self-contained — the replay engine evaluates against this bundle
    even if the live ``policy_bundles`` row has since been deleted or
    overwritten. ``None`` for pre-v0.9 receipts; the inner pair
    (``bundle_hash``, ``bundle_yaml``) may be ``None`` when no policy
    was active at emission. See ``replay_receipt`` and the replay
    refusal codes for details."""


class ReceiptList(BaseModel):
    """Paged list of receipts. `next_cursor` is None when there are no
    further results."""

    receipts: list[Receipt] = Field(default_factory=list)
    next_cursor: str | None = None


class ReceiptVerifyResult(BaseModel):
    """Result of ``GET /v1/receipts/{id}/verify`` (v0.9+ #157).

    ``valid`` is the verdict:

    - ``True`` — HMAC matches the canonical body. ``reason == "ok"``.
    - ``False`` — math checked, signature does not cover the body.
      ``reason == "signature_mismatch"``.
    - ``None`` — verdict could not be determined. ``reason`` is one
      of:

      * ``"no_signature"`` — receipt is unsigned (pre-v0.9 or
        tenant didn't opt in to signing).
      * ``"key_unavailable"`` — the ``key_id`` rotated out of
        operator config; receipt is no longer verifiable on this
        binary. Never a 500.
      * ``"unsupported_algorithm"`` — receipt signed under a
        canonical-form / algorithm variant this binary doesn't
        implement (forward-compat).

    Comparison is constant-time on the server side; the signing
    key bytes never appear on the response."""

    valid: bool | None
    key_id: str | None
    algorithm: str | None
    reason: str


class ReceiptReplayDiff(BaseModel):
    """Structural diff envelope returned by
    ``POST /v1/receipts/{id}/replay``. Entries are matched by their
    ``memory_id`` / ``episode_id`` so re-ranking the same entry is
    reported under ``common``, not as add+remove. See
    ``docs/replay.md`` in the server repo for the design rationale."""

    context_hash: dict[str, Any] = Field(default_factory=dict)
    """``{"original": "<sha>", "replay": "<sha>", "changed": bool}``."""
    selected_entries: dict[str, Any] = Field(default_factory=dict)
    """``{"added": [...], "removed": [...], "common": int}``."""
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    """``{"added": [...], "removed": [...]}``."""


class ReceiptReplayResult(BaseModel):
    """Response from ``POST /v1/receipts/{id}/replay`` (v0.9+ #159).

    Semantic: current code + original policy. Replay re-runs the
    original retrieval against the *current* memory state but with
    the *original* policy bundle frozen on the receipt's
    ``policy_snapshot``. The original receipt is never modified;
    ``replay_receipt_id`` points at a new ``mode="as_of_replay"``
    receipt linked back to the source via ``parent_receipt_id``.

    ``replay_receipt_id`` is ``None`` when the replay-receipt write
    itself failed (rare, fail-open path). The ``diff`` envelope is
    still authoritative in that case — the original entries are
    reported under ``removed`` so the caller can still see what
    was on the source."""

    original_receipt_id: str
    replay_receipt_id: str | None
    diff: ReceiptReplayDiff


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


# ---------------------------------------------------------------------------
# Support-agent models
# ---------------------------------------------------------------------------

class HealthFactor(BaseModel):
    """One explainable factor behind a customer health score."""

    signal: str
    impact: int
    detail: str


class Health(BaseModel):
    """Customer health score (0-100) with the factors that drove it."""

    subject_id: str
    score: int
    state: str  # healthy | watch | at_risk
    factors: list[HealthFactor] = Field(default_factory=list)


class SessionSLA(BaseModel):
    """SLA metrics for a single support session."""

    session_id: str
    status: str  # resolved | open
    first_message_at: str | None = None
    first_response_at: str | None = None
    resolved_at: str | None = None
    first_response_seconds: float | None = None
    resolution_seconds: float | None = None
    open_duration_seconds: float | None = None
    first_response_breached: bool = False
    resolution_breached: bool = False


class SLASummary(BaseModel):
    """Aggregate SLA metrics for a subject across all of its sessions."""

    subject_id: str
    total_sessions: int
    resolved_sessions: int
    open_sessions: int
    avg_first_response_seconds: float | None = None
    avg_resolution_seconds: float | None = None
    first_response_breach_count: int = 0
    resolution_breach_count: int = 0
    sessions: list[SessionSLA] = Field(default_factory=list)


class ResolutionSummaryItem(BaseModel):
    """A prior resolution surfaced inside a handoff brief."""

    session_id: str
    status: str
    summary: str | None = None
    resolved_at: datetime | None = None


class Handoff(BaseModel):
    """Structured escalation brief — the handoff context pack."""

    subject_id: str
    session_id: str
    reason: str
    generated_at: datetime
    customer_summary: str = ""
    active_issue: str = ""
    attempted_steps: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    resolution_history: list[ResolutionSummaryItem] = Field(default_factory=list)
    recent_context: list[str] = Field(default_factory=list)
    health_score: int | None = None
    health_state: str | None = None  # healthy | watch | at_risk
    health_factors: list[HealthFactor] = Field(default_factory=list)
    handoff_notes: str = ""
    token_estimate: int = 0
    provenance: dict[str, Any] = Field(default_factory=dict)
    receipt_id: str | None = None
    receipt_emitted: bool = False


class Resolution(BaseModel):
    """Resolution tracking record for a support session."""

    id: uuid.UUID
    subject_id: str
    session_id: str
    status: str
    resolution_summary: str | None = None
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SuggestedLabelMemory(BaseModel):
    """A memory carrying auto-derived suggested labels, for operator review (v0.9 #158)."""

    id: str
    subject_id: str
    tenant_id: str | None = None
    kind: str
    content: str
    summary: str
    suggested_labels: list[str]
    sensitivity_labels: list[str]
    created_at: str


class SuggestedLabelsList(BaseModel):
    """Paginated list of memories with suggested labels — the admin review surface."""

    memories: list[SuggestedLabelMemory]
    total: int
    limit: int
    offset: int
    catalogue: list[dict[str, str]] = Field(default_factory=list)


class PromoteLabelsResult(BaseModel):
    """Result of promoting suggested labels into authoritative sensitivity_labels (v0.9 #160)."""

    memory_id: str
    promoted: list[str]
    sensitivity_labels: list[str]
    suggested_labels: list[str]
