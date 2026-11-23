# Development

## Repository layout

- `src/delegation_core/`: main Python package (MCP server, HTTP daemon, SQLite index, embeddings, ingestion, scheduler, alerts, hooks, CLI, and `cores/`).
- `src/delegation_core/graph/`: vendored code-graph pipeline adapted from Graphify (`THIRD_PARTY_LICENSES/`).
- `dashboard/`: native Tauri desktop application (see `dashboard/README.md`).
- `scripts/gerar_referencia.py`: generates all pages in `docs/reference/` directly from the codebase.
- `tests/`: pytest suite covering tools, SQLite index, ingestion, hooks, security, and documentation drift.

For the architectural map of modules, see [MAPA.md](MAPA.md) and the generated [Reference](reference/README.md).

## Running tests

Install the development extra and run pytest:

```bash
pip install -e ".[dev]"
pytest
```

Targeted suites run quickly during development:

```bash
pytest tests/test_capability_registry.py
pytest tests/test_ingest*.py
```

## Keeping generated documentation in sync

Everything enumerable (MCP tools, feature flags, configuration keys, CLI commands, scheduled tasks, alert rules, dashboard HTTP routes, environment variables, and tool errors) is generated from code into `docs/reference/`.

Whenever you add, rename, or change a tool, config key, CLI command, or route:

1. Regenerate the reference pages:
   ```bash
   python3 scripts/gerar_referencia.py
   ```
2. Run the test suite. The drift tests fail if `docs/reference/` or `capabilities()` no longer matches the code.

## Continuous integration

GitHub Actions runs the test suite across **Linux, macOS, and Windows**. Watch out for cross-platform edge cases:

- Use `pathlib.Path` rather than hardcoded `/` separators.
- Normalize line endings (`\n`) when comparing or restoring Markdown/frontmatter across Windows and POSIX.
- Avoid assuming `/bin/sh` or POSIX-only process flags in cross-platform tests.

## Releasing a new version

1. Ensure CI is green on Linux, macOS, and Windows.
2. Regenerate `docs/reference/` with `scripts/gerar_referencia.py` and verify zero drift.
3. Update `version` in `pyproject.toml` and add the release entry to `CHANGELOG.md`.
4. Merge via PR into `master` and create the annotated release tag (`vX.Y.Z`).
