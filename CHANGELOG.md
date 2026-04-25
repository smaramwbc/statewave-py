# Changelog

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
