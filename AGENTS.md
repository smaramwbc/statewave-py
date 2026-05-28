# Agent guardrails

Workspace-wide rules for autonomous agents (e.g. the GitHub Copilot
coding agent) and anyone editing here. The complete set and rationale
live in the canonical copy: `statewave-docs/AGENTS.md`.

## Hard rules

- **No maturity overclaiming.** Never "GA", "production-ready",
  "enterprise-ready", "hardened", or "battle-tested". The canonical
  phrase is "first stable public developer release." Benchmark or perf
  claims must be source-backed and caveated.
- **Public repos address users, not owners.** No owner TODOs, "before
  launch" notes, or pricing placeholders in public docs.
- **Neutral brand voice.** No personal or founder names in public copy;
  sign off as "Statewave team" or not at all.
- **Proof figures are mirrored.** Test counts, eval assertion/test
  counts, and the support-workflow benchmark score have one source of
  truth (`statewave-docs/tools/_proof_figures.py`) and a release-time
  check (`check-proof-figures.py`). Change the source, never one surface.
- **Versions are independent per package.** A core `0.9.x` next to an
  SDK `0.10.x` is correct, not drift. Do not reconcile version numbers.
- **Launch copy is intentionally ahead.** The launch posts are
  pre-written for the unreleased v1.0; do not "correct" them down to the
  current version.
- **Respect the v1.0 launch freeze.** No tags, releases, or version
  bumps, and no backend/SDK/connector code changes until the launch is
  authorized. Docs, lint, and consistency fixes are fine.

## Git hygiene

- No self-attribution in commits or PR descriptions.
- Commit identity: `smaramwbc
  <145447586+smaramwbc@users.noreply.github.com>`.
- Rebase merges only (`gh pr merge --rebase --delete-branch`).
