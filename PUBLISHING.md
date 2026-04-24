# Publishing statewave-py

Releases are automated via GitHub Actions. Pushing a `v*` tag triggers CI, builds the package, publishes to PyPI, and creates a GitHub Release.

## Release process

1. **Update version** in both `pyproject.toml` and `statewave/__init__.py`
2. **Update CHANGELOG.md** with the new version and date
3. **Commit** to main:
   ```bash
   git add pyproject.toml statewave/__init__.py CHANGELOG.md
   git commit -m "release: v0.X.Y"
   git push
   ```
4. **Wait for CI to pass** on the main branch push
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
- [ ] Version bumped in `pyproject.toml`
- [ ] Version bumped in `statewave/__init__.py`
- [ ] CHANGELOG.md updated with version and date
- [ ] README.md is accurate
- [ ] CI passes on main before tagging

## Post-release verification

- [ ] GitHub Release exists at `https://github.com/smaramwbc/statewave-py/releases`
- [ ] PyPI package updated: `pip install statewave-py==0.X.Y`
- [ ] Import works: `python -c "import statewave; print(statewave.__version__)"`
- [ ] CHANGELOG version matches tag

## Required GitHub settings

- **PyPI trusted publishing** must be configured:
  1. Go to https://pypi.org → Your projects → `statewave-py` → Settings → Publishing
  2. Add publisher: owner `smaramwbc`, repo `statewave-py`, workflow `release.yml`

## Manual publish (fallback)

If automation fails, publish manually:

```bash
pip install build twine
python -m build
twine check dist/*
twine upload dist/*
```
