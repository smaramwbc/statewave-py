# statewave-py

Official Python SDK for [Statewave](https://github.com/smaramwbc/statewave) — Memory OS for AI agents.

## Install

```bash
pip install statewave-py
```

## Quick start

```python
from statewave import StatewaveClient

with StatewaveClient("http://localhost:8100") as sw:
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
    )

    # Compile memories (idempotent)
    result = sw.compile_memories("user-42")
    print(f"Created {result.memories_created} memories")

    # Retrieve ranked, token-bounded context
    ctx = sw.get_context("user-42", task="Help with billing", max_tokens=300)
    print(ctx.assembled_context)

    # Search memories by kind
    facts = sw.search_memories("user-42", kind="profile_fact")
    for m in facts.memories:
        print(f"  [{m.kind}] {m.content}")

    # Get timeline
    timeline = sw.get_timeline("user-42")
    print(f"{len(timeline.episodes)} episodes, {len(timeline.memories)} memories")

    # Delete all subject data
    sw.delete_subject("user-42")
```

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

## Models

All response types are Pydantic models with full type hints:

- `Episode` — raw interaction record
- `Memory` — compiled memory with provenance
- `CompileResult` — compilation response
- `SearchResult` — search response
- `ContextBundle` — assembled context with facts, episodes, provenance
- `Timeline` — chronological subject history
- `DeleteResult` — deletion confirmation

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

Apache-2.0
