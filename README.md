# Statewave Python SDK

[![CI](https://github.com/smaramwbc/statewave-py/workflows/CI/badge.svg)](https://github.com/smaramwbc/statewave-py/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/statewave)](https://pypi.org/project/statewave/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Statewave Python SDK — memory runtime for AI agents and applications. The TypeScript SDK lives at [`@statewavedev/sdk`](https://github.com/smaramwbc/statewave-ts).

> **Part of the Statewave ecosystem:** [Server](https://github.com/smaramwbc/statewave) · **Python SDK** · [TypeScript SDK](https://github.com/smaramwbc/statewave-ts) · [Connectors](https://github.com/smaramwbc/statewave-connectors) · [Docs](https://github.com/smaramwbc/statewave-docs) · [Examples](https://github.com/smaramwbc/statewave-examples) · [Website + demo](https://statewave.ai) · [Admin](https://github.com/smaramwbc/statewave-admin)
>
> 📋 **Issues & feature requests:** [statewave/issues](https://github.com/smaramwbc/statewave/issues) (centralized tracker)

> **New to Statewave?** This SDK is a thin client for a running **Statewave
> server**. If you don't have one yet, the
> [Getting Started guide](https://github.com/smaramwbc/statewave-docs/blob/main/getting-started.md)
> brings one up with Docker Compose in about 5 minutes. Every example below
> assumes a server reachable at `http://localhost:8100`.

## Install

```bash
pip install statewave
```

## Quick start

```python
from statewave import StatewaveClient

# Basic (no auth)
with StatewaveClient("http://localhost:8100") as sw:
    ...

# With authentication and tenant
with StatewaveClient(
    "http://localhost:8100",
    api_key="your-key",
    tenant_id="acme",
) as sw:
    # Record an episode
    sw.create_episode(
        subject_id="user-42",
        source="support-chat",
        type="conversation",
        payload={
            "messages": [
                {"role": "user", "content": "My name is Alice and I work at Globex."},
                {"role": "assistant", "content": "Welcome Alice!"},
            ]
        },
        session_id="ticket-8842",  # optional — pins the episode to a session (1.0+)
    )

    # Compile memories (idempotent)
    result = sw.compile_memories("user-42")
    print(f"Created {result.memories_created} memories")

    # Retrieve ranked, token-bounded context
    ctx = sw.get_context("user-42", task="Help with billing", max_tokens=300)
    print(ctx.assembled_context)

    # Batch ingestion (up to 100)
    sw.create_episodes_batch([
        {"subject_id": "user-42", "source": "crm", "type": "note", "payload": {"text": "Prefers email"}},
        {"subject_id": "user-42", "source": "crm", "type": "note", "payload": {"text": "Enterprise plan"}},
    ])

    # Search memories by kind
    facts = sw.search_memories("user-42", kind="profile_fact")
    for m in facts.memories:
        print(f"  [{m.kind}] {m.content}")

    # Semantic search (requires embeddings)
    results = sw.search_memories("user-42", query="billing", semantic=True)

    # List all known subjects
    subjects = sw.list_subjects()
    for s in subjects.subjects:
        print(f"  {s.subject_id}: {s.episode_count} episodes, {s.memory_count} memories")

    # Get timeline
    timeline = sw.get_timeline("user-42")
    print(f"{len(timeline.episodes)} episodes, {len(timeline.memories)} memories")

    # Delete all subject data
    sw.delete_subject("user-42")
```

## Governance & audit (v0.8+)

The SDK surfaces the [state-assembly receipts](https://github.com/smaramwbc/statewave-docs/blob/main/receipts.md) and [sensitivity-labels / policy](https://github.com/smaramwbc/statewave-docs/blob/main/sensitivity-labels.md) layer added in server v0.8, plus the v0.9 [HMAC signing](https://github.com/smaramwbc/statewave/blob/main/docs/state-assembly-receipts.md) and [as-of replay](https://github.com/smaramwbc/statewave/blob/main/docs/replay.md) surfaces.

```python
from statewave import StatewaveClient

with StatewaveClient("http://localhost:8100", tenant_id="acme", api_key="…") as sw:
    # Per-request opt-in for an immutable audit receipt of the assembly.
    # caller_id / caller_type feed the sensitivity-label policy engine
    # — when the tenant config sets require_caller_identity=true, missing
    # values 401.
    bundle = sw.get_context(
        subject_id="user-42",
        task="What plan is this customer on?",
        emit_receipt=True,
        caller_id="agent-7",
        caller_type="support_agent",
    )

    if bundle.receipt_id:
        # Receipts are ULID-addressable, tenant-scoped, append-only.
        receipt = sw.get_receipt(bundle.receipt_id)
        # output.context_hash is a SHA-256 of the bytes delivered to the
        # agent — recompute from bundle.assembled_context to verify integrity.
        print(receipt.output["context_hash"])
        print(f"{len(receipt.selected_entries)} entries influenced this bundle")

    # List receipts for a subject, cursor-paginated, newest-first.
    for receipt in sw.list_receipts(subject_id="user-42", limit=10).receipts:
        print(receipt.receipt_id, receipt.task)

    # Verify the HMAC signature on a stored receipt (v0.9+).
    # `valid` is True | False | None — see ReceiptVerifyResult for the
    # full reason vocabulary (no_signature / key_unavailable / etc.).
    verdict = sw.verify_receipt(bundle.receipt_id)
    if verdict.valid is True:
        print(f"signature OK — signed by {verdict.key_id}")
    elif verdict.valid is False:
        print(f"signature mismatch — body may have been tampered with")
    else:
        print(f"verdict undetermined: {verdict.reason}")

    # Replay the receipt against current memories using the original
    # policy bundle captured on the receipt (v0.9+). Returns a diff
    # envelope showing what changed since emission. Pre-v0.9 receipts
    # raise StatewaveUnreplayableError(reason="missing_policy_snapshot").
    from statewave import StatewaveUnreplayableError
    try:
        replay = sw.replay_receipt(bundle.receipt_id)
        if replay.diff.context_hash["changed"]:
            print(f"replay differs from original: new id {replay.replay_receipt_id}")
    except StatewaveUnreplayableError as exc:
        # exc.reason ∈ {"missing_policy_snapshot", "nested_replay", "invalid_snapshot"}
        print(f"replay refused: {exc.reason}")

    # Set per-memory sensitivity labels (server normalizes — dedup, lowercase, trim).
    # Memories with labels become subject to any active policy bundle for the tenant.
    updated = sw.set_memory_labels(memory_id="mem-uuid", labels=["pii", "financial"])
    print(updated.sensitivity_labels)  # → ["financial", "pii"]

    # Auto-labeling review workflow (server v0.9 #158/#160; needs
    # STATEWAVE_AUTO_LABELING_ENABLED=true). Detectors stamp *suggested* labels;
    # an operator reviews and promotes them into authoritative sensitivity_labels.
    review = sw.list_suggested_labels(label="financial.card")
    for m in review.memories:
        print(m.id, m.suggested_labels)  # → e.g. ["financial.card"]
    promoted = sw.promote_suggested_labels(memory_id="mem-uuid", labels=["financial.card"])
    print(promoted.sensitivity_labels)  # now authoritative
```

Receipts and the policy engine cooperate: every assembly call records its policy decisions into `receipt.policy.filters_applied` (one entry per memory the policy fired on) and `receipt.policy.filters_skipped` (per-rule summary of what didn't fire). In `log_only` mode (the tenant default) the receipt is the full audit trail without filtering; under `enforce` denied memories are dropped before they reach the assembly and the deny is still recorded. See [`receipts.md`](https://github.com/smaramwbc/statewave-docs/blob/main/receipts.md) and [`sensitivity-labels.md`](https://github.com/smaramwbc/statewave-docs/blob/main/sensitivity-labels.md) for the full schemas and policy YAML format.

## Support-agent endpoints

Statewave's support wedge — customer health scoring, SLA tracking, resolution state, and structured escalation briefs — is exposed through ergonomic methods on both the sync and async clients (server v0.6+).

```python
from statewave import StatewaveClient

with StatewaveClient("http://localhost:8100") as sw:
    # Customer health score (0-100) with the explainable factors behind it.
    health = sw.get_health("customer:globex")
    print(f"{health.score}/100 — {health.state}")
    for f in health.factors:
        print(f"  {f.signal}: {f.impact:+d} ({f.detail})")

    # SLA metrics — first-response / resolution times and breach counts.
    # Thresholds are optional; they default server-side to 5 min / 24 h.
    sla = sw.get_sla(
        "customer:globex",
        first_response_threshold_minutes=10,
        resolution_threshold_hours=48,
    )
    print(f"{sla.resolved_sessions}/{sla.total_sessions} resolved, "
          f"{sla.resolution_breach_count} SLA breaches")

    # Track resolution state for a session (upserts by subject + session).
    sw.create_resolution(
        "customer:globex",
        "ticket-8842",
        status="resolved",
        resolution_summary="Issued refund for the duplicate charge",
    )

    # List resolutions, optionally filtered by status.
    open_items = sw.list_resolutions("customer:globex", status="open")

    # Generate a handoff context pack for escalation or shift change.
    # handoff_notes is a pre-rendered markdown brief for human or LLM use.
    handoff = sw.create_handoff(
        "customer:globex",
        "ticket-8842",
        reason="escalation",
        caller_id="agent-7",
        caller_type="support_agent",
    )
    print(handoff.handoff_notes)
```

`get_health`, `get_sla`, `create_resolution`, `list_resolutions`, and `create_handoff` exist on `AsyncStatewaveClient` too, with identical signatures. `create_handoff` shares `get_context`'s caller-identity gate — when the tenant config sets `require_caller_identity: true`, both `caller_id` and `caller_type` are mandatory.

## Async client

```python
from statewave import AsyncStatewaveClient

async with AsyncStatewaveClient("http://localhost:8100") as sw:
    ctx = await sw.get_context("user-42", task="Help with billing")
    print(ctx.assembled_context)
```

## Error handling

```python
from statewave import StatewaveClient, StatewaveAPIError, StatewaveConnectionError

try:
    sw = StatewaveClient("http://localhost:8100")
    sw.compile_memories("user-42")
except StatewaveAPIError as e:
    print(f"API error [{e.status_code}]: {e.code} — {e.message}")
    print(f"Request ID: {e.request_id}")
except StatewaveConnectionError:
    print("Cannot connect to Statewave server")
```

## Where does data go?

The SDK is a thin client over the Statewave HTTP API. What leaves the network is determined by the **server's** compiler and embedding configuration, not by the SDK:

- Default deployment (heuristic compiler, no embeddings) — nothing leaves your infrastructure.
- LLM compiler or hosted embeddings — the server sends content to the provider you configure.

See [Privacy & Data Flow](https://github.com/smaramwbc/statewave-docs/blob/main/architecture/privacy-and-data-flow.md) for the full breakdown.

## Models

All response types are Pydantic models with full type hints:

- `Episode` — raw interaction record
- `Memory` — compiled memory with provenance + `sensitivity_labels`
- `CompileResult` — compilation response
- `SearchResult` — search response
- `ContextBundle` — assembled context with facts, episodes, provenance, optional `receipt_id` / `receipt_emitted`
- `Timeline` — chronological subject history
- `DeleteResult` — deletion confirmation
- `BatchCreateResult` — batch ingestion response
- `SubjectSummary` — subject with episode/memory counts
- `ListSubjectsResult` — paginated subject listing
- `Receipt` — state-assembly audit artifact (v0.8+) — ULID-addressable, content-hash integrity, per-entry supersession status; v0.9 added HMAC signature fields (`receipt_signature_key_id`, `receipt_signature_algorithm`), `policy_snapshot` for replay, and `region` for residency
- `ReceiptVerifyResult` — `valid` (True | False | None) + `key_id` + `algorithm` + `reason` for the v0.9 HMAC verify endpoint
- `ReceiptReplayResult` / `ReceiptReplayDiff` — original + replay receipt ids plus the structural diff envelope from `POST /v1/receipts/{id}/replay` (v0.9)
- `StatewaveUnreplayableError(reason=…)` — raised by `replay_receipt(…)` on HTTP 422; `reason ∈ {"missing_policy_snapshot", "nested_replay", "invalid_snapshot"}`
- `ReceiptList` — cursor-paginated receipt listing
- `Health` / `HealthFactor` — customer health score and its explainable factors
- `SLASummary` / `SessionSLA` — SLA metrics, aggregate and per-session
- `Handoff` / `ResolutionSummaryItem` — handoff context pack and its prior-resolution items
- `Resolution` — resolution tracking record

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

Apache-2.0
