# Publishing statewave-py to PyPI

## Pre-flight

- [ ] All tests pass: `pytest`
- [ ] Version bumped in `pyproject.toml` and `statewave/__init__.py`
- [ ] CHANGELOG.md updated
- [ ] README.md accurate
- [ ] `git tag v{version}`

## Build & publish

```bash
pip install build twine
python -m build
twine check dist/*
twine upload dist/*          # or: twine upload --repository testpypi dist/*
```

## Verify

```bash
pip install statewave-py=={version}
python -c "import statewave; print(statewave.__version__)"
```
