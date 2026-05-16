# Changelog

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
