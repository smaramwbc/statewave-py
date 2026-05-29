# AGENTS.md — guide for contributors and coding agents

A short orientation for humans and AI coding agents (GitHub Copilot, Claude,
Cursor, …) working in **statewave-py** — the Python SDK for Statewave
(`pip install statewave`), a sync + async client over the `/v1` API.

## Setup, build, test

See the [README](README.md) for canonical setup. In short:

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

Run `ruff` and `pytest` before opening a PR.

## Conventions

- **Code style & testing:** see
  [statewave-docs/dev/conventions.md](https://github.com/smaramwbc/statewave-docs/blob/main/dev/conventions.md).
- **This SDK versions independently** of the server and the TypeScript SDK; the
  compatibility axis is the `/v1` API contract, not a shared version number.
  Don't align version strings across packages.
- **Keep claims accurate and modest** in docs and examples; avoid unqualified
  superlatives.

## Pull requests

Keep PRs focused, add tests for behavior changes, and make sure `ruff` and
`pytest` pass.

## Optional: give your agent memory of this repo (with Statewave)

This project dogfoods Statewave. The easiest way to give your assistant a
queryable project brain for this repo is the **Statewave IDE Companion**
extension for **VS Code / Cursor** (publisher `statewavedev`) — install it from
your editor's extensions marketplace. It exposes your workspace, docs, git
state, and structure to Copilot / Cursor / Claude over MCP and **registers the
MCP server for you** (no manual config); it just needs a Statewave server to
talk to (a one-file `docker compose up`). See the
[extension README](https://github.com/smaramwbc/statewave-connectors/blob/main/packages/vscode-extension/README.md).

Prefer to wire it up by hand, or use another MCP client? Run the
[Statewave MCP server](https://github.com/smaramwbc/statewave-docs/blob/main/connectors/mcp.md)
(`@statewavedev/mcp-server`) directly and query subject `repo:smaramwbc/statewave-py`.
