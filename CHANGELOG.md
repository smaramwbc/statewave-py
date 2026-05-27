# Changelog

## 0.10.2 (2026-05-27)

### Added — `session_id` on `create_episode` (closes [statewave#174](https://github.com/smaramwbc/statewave/issues/174))

`create_episode` and `AsyncStatewaveClient.create_episode` accept an optional `session_id` keyword argument that is forwarded to `POST /v1/episodes`. The server has accepted this field since the session-aware ranking work, but the SDK signature was missing it — callers had to drop down to raw HTTP to use the surface. v0.9.4 launch-readiness picked this up as a visible REST-contract / SDK-signature mismatch worth closing before v1.0.

- `session_id: str | None = None` keyword-only argument on both client classes.
- Field is omitted from the request body when `None` (matches the server's "no session pin" semantics — the server does not auto-assign).
- Round-trip is write-only: the server's `Episode` response does not echo `session_id`, so the `Episode` model is unchanged.
- Pure-additive surface change. No breaking move; existing call sites continue to work unchanged.

### Tests

- `test_create_episode_forwards_session_id` (sync) and the async counterpart in `tests/test_episodes.py` assert the field reaches the request body exactly once when set, and that absence keeps the previous wire shape byte-for-byte unchanged.

## 0.10.1 (2026-05-26)

### Added — v0.9 receipt-governance convenience methods (closes [statewave#169](https://github.com/smaramwbc/statewave/issues/169))

Closes the gap where the v0.9 server release (`statewave` v0.9.1 / v0.9.2) added `GET /v1/receipts/{id}/verify` and `POST /v1/receipts/{id}/replay` but the SDK at v0.10.0 only knew about pre-v0.9 receipt endpoints.

- **`verify_receipt(receipt_id) -> ReceiptVerifyResult`** on both `StatewaveClient` (sync) and `AsyncStatewaveClient` (async). Calls `GET /v1/receipts/{id}/verify` and returns a typed result with `valid` ∈ `{True, False, None}` plus `key_id`, `algorithm`, and a structured `reason`. Comparison is constant-time on the server side; signing key bytes never appear on the response.
- **`replay_receipt(receipt_id) -> ReceiptReplayResult`** on both clients. Calls `POST /v1/receipts/{id}/replay` and returns the original/replay receipt ids plus a typed `ReceiptReplayDiff` envelope (`context_hash`, `selected_entries.{added,removed,common}`, `filters_applied.{added,removed}`). The original receipt is never modified — replay only emits a new linked child.
- **`StatewaveUnreplayableError(reason=…)`** (subclass of `StatewaveAPIError`) wraps the server's HTTP 422 refusal codes so callers can `except StatewaveUnreplayableError as exc: ... exc.reason` instead of parsing error code strings. `reason ∈ {"missing_policy_snapshot", "nested_replay", "invalid_snapshot"}` — the documented refusal vocabulary. A new `unreplayable.<reason>` code from a future server is preserved through the generic `StatewaveAPIError` path.

### Changed — `Receipt` model gains v0.9 governance fields

The `Receipt` Pydantic model now accepts the v0.9 fields the server began emitting in v0.9.1, all `Optional[T] = None` so pre-v0.9 receipts continue to validate cleanly:

- `receipt_signature_key_id: str | None` — operator key id used to sign (#157).
- `receipt_signature_algorithm: str | None` — e.g. `"hmac-sha256-canonical-v1"` (#157).
- `policy_snapshot: dict[str, Any] | None` — embedded bundle YAML + hash + capture timestamp the replay engine evaluates against (#159).
- `mode` docstring updated to call out the new `"as_of_replay"` value.

Without this change, pre-v0.10.1 clients hitting a v0.9.1+ server would silently drop these fields.

### Changed — PyPI Development Status classifier

`Development Status :: 3 - Alpha` → `Development Status :: 4 - Beta`. The SDK has shipped major versions (v0.5–v0.10) against a production server and covers the entire v0.9 API surface; the Alpha label was stale.

### Notes

- Purely additive — no existing method, model, behaviour, or wire contract changes. Upgrading from v0.10.0 should be a drop-in replacement.
- Version-aligned with `statewave-ts` v0.10.1, which lands the equivalent TypeScript surface in parallel.
- Part of the `statewave` v0.9.2 stabilization patch — see [v0.9.2 release notes](https://github.com/smaramwbc/statewave/releases/tag/v0.9.2) for the coordinated context.

## 0.10.0 (2026-05-21)

### Added — support-agent SDK methods

Ergonomic wrappers for the support-agent endpoints (server v0.6+), on **both** the sync `StatewaveClient` and the `AsyncStatewaveClient`, so the support wedge no longer needs raw `httpx` calls alongside the SDK:

- `get_health(subject_id) -> Health` — customer health score (0-100) with the explainable factors behind it.
- `get_sla(subject_id, *, first_response_threshold_minutes=None, resolution_threshold_hours=None) -> SLASummary` — first-response / resolution times and breach counts, aggregated across the subject's sessions. Thresholds fall back to the server defaults (5 min / 24 h).
- `create_handoff(subject_id, session_id, *, reason=None, max_tokens=None, ...) -> Handoff` — generate a structured escalation brief. Shares `get_context`'s caller-identity gate (`caller_id` / `caller_type`).
- `create_resolution(subject_id, session_id, *, status="open", resolution_summary=None, metadata=None) -> Resolution` — create or update a resolution record; upserts by `subject_id` + `session_id`.
- `list_resolutions(subject_id, *, status=None) -> list[Resolution]` — list resolution records for a subject, optionally filtered by status.

New Pydantic models, all exported from the package root: `Health`, `HealthFactor`, `SLASummary`, `SessionSLA`, `Handoff`, `ResolutionSummaryItem`, `Resolution`.

### Notes

- Purely additive — no existing method, model, or behaviour changes. The HTTP wire contract is unchanged; these methods wrap endpoints the server has exposed since v0.6.
- Auth, tenant-scoping, retry/backoff, and error handling are inherited from the shared request path. The internal `_request` helper gained an `is_list` flag so the array-returning `GET /v1/resolutions` parses each element into a `Resolution`.
- Version kept aligned with the TypeScript SDK's `0.10.0` release.

## 0.9.0 (2026-05-16)

### Changed

- Version-alignment release only — **no API, behavior, or dependency changes**. The number is bumped to keep the workspace version consistent after the TypeScript SDK's independent 0.9.0 release (`@statewavedev/sdk`, breaking camelCase rename, statewave-ts#103). Code written against 0.8.0 works unchanged on 0.9.0.

## 0.8.0 (2026-05-14)

### Added — governance & audit surface

- `Receipt` and `ReceiptList` Pydantic models for the new state-assembly receipt schema (immutable per-retrieval audit artifact, ULID-addressable, content-hash integrity).
- `ContextBundle` gains optional `receipt_id` and `receipt_emitted` fields — defaults to `None` / `False` so responses from older servers parse cleanly.
- `Memory` gains optional `sensitivity_labels: list[str]` for the per-memory capability tags consumed by the policy layer; defaults to `[]` for older servers without the policy column.
- `StatewaveClient.get_context()` and `AsyncStatewaveClient.get_context()` accept five new optional kwargs:
  - `emit_receipt: bool | None` — opt-in per-request receipt emission (overridden by tenant config).
  - `query_id`, `task_id` — caller-supplied correlation ids recorded on the receipt.
  - `parent_receipt_id` — ULID of a parent receipt to chain multi-step tasks.
  - `caller_id`, `caller_type` — identity fed to the sensitivity-label policy evaluator. When the tenant config sets `require_caller_identity: true`, both are mandatory and missing values 401.
- New client methods on both sync + async clients:
  - `get_receipt(receipt_id) -> Receipt` — fetch one receipt by ULID.
  - `list_receipts(subject_id, since=, until=, cursor=, limit=) -> ReceiptList` — cursor-paginated, newest-first.
  - `set_memory_labels(memory_id, labels) -> Memory` — replace `sensitivity_labels`; server normalizes (dedup + lowercase + trim) and returns the canonical set.

### Notes

- All new fields and methods are backwards-compatible — clients calling 0.7-shape methods get the same responses they did before. Servers running pre-#49 don't emit receipts at all; servers pre-#50 don't enforce policy. The SDK degrades cleanly.
- Companion server release at the same version (statewave v0.8.0).

## 0.7.2 (2026-05-12)

- Version aligned with server v0.7.2 (per-kind memory TTL, Helm chart, query embedding cache, `MemoryStatus.tombstoned` rename).
- `__version__` bumped to 0.7.2.
- No client API changes — server-side release.

## 0.7.1 (2026-05-10)

- Package `description` aligned to the canonical Statewave tagline: "Official Python SDK for Statewave — the open-source memory runtime for AI agents."
- `__version__` bumped to 0.7.1.
- No client API changes.

## 0.7.0 — first public release on PyPI as `statewave`

- Install: `pip install statewave`
- Import: `from statewave import StatewaveClient`
- PyPI distribution name: `statewave`
- Description: "Statewave Python SDK"

## 0.6.2 (2026-05-02)

- Package metadata: `Homepage` and `Documentation` URLs now point to https://statewave.ai
- `__version__` synced to 0.6.2 (was lagging at 0.4.3)
- No client API changes

## 0.6.1 (2026-04-29)

- Version bump to align with server v0.6.1 (support-agent intelligence stack)
- Server now supports: resolution tracking, handoff packs, health scoring, SLA tracking, proactive alerts
- SDK convenience methods for new endpoints planned for 0.7.0
- No breaking changes to existing client methods

## 0.5.0 (2026-04-28)

- Async compile support: `compile_memories_async()`, `get_compile_status()`, `compile_memories_wait()`
- `CompileJob` model
- SDK retry with exponential backoff on 429/5xx

## 0.4.3 (2026-04-25)

- README updated with batch and subject listing examples
- Automated release workflow (tag-push trigger, CI gate, PyPI trusted publishing)
- PUBLISHING.md rewritten for automated process
- Lint fixes (unused imports)

## 0.4.0 (2026-04-24)

- Batch episode ingestion (`create_episodes_batch()`)
- Subject listing (`list_subjects()`)
- `BatchCreateResult`, `SubjectSummary`, `ListSubjectsResult` models
- `py.typed` marker for PEP 561
- PyPI-ready metadata (author, URLs, classifiers, keywords)

## 0.3.5 (2026-04-24)

- Auth support (`api_key` constructor param)
- Multi-tenant support (`tenant_id` constructor param)
- Semantic search support (`semantic` param on `search_memories`)
- Async client (`AsyncStatewaveClient`)
- Custom exception hierarchy with request-ID propagation

## 0.2.0

- Initial public release
- Sync client with all v1 endpoints
- Pydantic response models
