# Publishing the Statewave Python SDK

> Distributed on PyPI as **`statewave`**. The import path is `from statewave import ...`.

Releases are automated via GitHub Actions. Pushing a `v*` tag triggers CI, builds the package, publishes to PyPI, and creates a GitHub Release.

## One-time PyPI setup

PyPI **trusted publishing** is configured for the project:

- Project: `statewave`
- Owner: `smaramwbc`
- Repository: `statewave-py`
- Workflow: `release.yml`

No PyPI token is needed in CI — the workflow authenticates via OIDC.

## Release process

1. **Update version** in both `pyproject.toml` and `statewave/__init__.py`.
2. **Update CHANGELOG.md** with the new version and date.
3. **Commit** to main:
   ```bash
   git add pyproject.toml statewave/__init__.py CHANGELOG.md
   git commit -m "release: v0.X.Y"
   git push
   ```
4. **Wait for CI to pass** on the main branch push.
5. **Tag and push**:
   ```bash
   git tag v0.X.Y
   git push --tags
   ```
6. The `release.yml` workflow will:
   - Run CI (lint + tests)
   - Build sdist and wheel
   - Publish to PyPI via trusted publishing
   - Create a GitHub Release with artifacts

## Pre-flight checklist

- [ ] All tests pass locally: `pytest tests/ -v`
- [ ] Build is clean: `python -m build && python -m twine check dist/*`
- [ ] Fresh-venv install works: `pip install dist/*.whl && python -c "import statewave; print(statewave.__version__)"`
- [ ] Version bumped in `pyproject.toml`
- [ ] Version bumped in `statewave/__init__.py`
- [ ] CHANGELOG.md updated with version and date
- [ ] README.md is accurate
- [ ] CI passes on main before tagging

## Post-release verification

- [ ] GitHub Release exists at `https://github.com/smaramwbc/statewave-py/releases`
- [ ] PyPI package updated: `pip install statewave==0.X.Y`
- [ ] Import works: `python -c "import statewave; print(statewave.__version__)"`
- [ ] CHANGELOG version matches tag

## Manual publish (fallback)

If trusted publishing fails:

```bash
pip install --upgrade build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*    # requires a PyPI API token with publish rights
```
