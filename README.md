# statewave-py

Official Python SDK for [Statewave](https://github.com/smaramwbc/statewave) — Memory OS for AI agents.

## Install

```bash
pip install statewave-py
```

## Quick start

```python
from statewave import StatewaveClient

sw = StatewaveClient("http://localhost:8100")

# Record an episode
episode = sw.create_episode(
    subject_id="user-42",
    source="chat",
    type="conversation",
    payload={"messages": [{"role": "user", "content": "My name is Alice"}]},
)

# Compile memories
result = sw.compile_memories("user-42")
print(f"Created {result.memories_created} memories")

# Retrieve context for an AI call
ctx = sw.get_context("user-42", task="Help the user with their account")
print(ctx.assembled_context)

# Search memories
search = sw.search_memories("user-42", kind="profile_fact")
for m in search.memories:
    print(f"  {m.kind}: {m.content}")

# Delete subject data
sw.delete_subject("user-42")
```

## License

Apache-2.0
