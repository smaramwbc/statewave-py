# Publishing the Statewave Python SDK

> Distributed on PyPI as **`statewave`** (renamed from `statewave-py` before public launch). The import path is `from statewave import ...` and was always that — only the PyPI distribution name changed.

Releases are automated via GitHub Actions. Pushing a `v*` tag triggers CI, builds the package, publishes to PyPI, and creates a GitHub Release.

## One-time PyPI setup (before the first `statewave` release)

1. Reserve the **`statewave`** PyPI name (we verified it's available; first push will claim it).
2. Configure PyPI **trusted publishing** for the new project:
   - <https://pypi.org/manage/account/publishing/> → Add a pending publisher for project `statewave`, repo `smaramwbc/statewave-py`, workflow `release.yml`, environment (optional) blank.
3. After the first publish, confirm membership at <https://pypi.org/project/statewave/> → Manage → Collaborators.

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
   - Publish to PyPI via trusted publishing (no token needed)
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

## Legacy `statewave-py` PyPI handling

The pre-public `statewave-py` PyPI package (last published at 0.6.2) is no longer used. PyPI does not support a one-line "deprecate" command the way npm does, but you should:

1. Yank the old releases as-needed (`pip` will still resolve them; `--pre` semantics are unchanged) — yanking is reversible.
2. Update the project description on PyPI (`statewave-py` → "Renamed to `statewave`. Run `pip install statewave`."), pushed via a metadata-only release if needed.
3. Do **not** publish 0.7.x under the old name.

## Manual publish (fallback)

If trusted publishing fails:

```bash
pip install --upgrade build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*    # requires a PyPI API token with publish rights for `statewave`
```
