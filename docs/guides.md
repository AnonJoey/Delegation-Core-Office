# Guides

Task-oriented procedures using real CLI commands and MCP tools. For every flag and option, consult [Command line](reference/cli.md) and [Configuration keys](reference/config.md).

## Update, roll back, or uninstall

### Update from GitHub

```bash
delegation-core update
```

`update` backs up the current installation, pulls the target version, updates dependencies, and restarts the daemon while preserving `~/.delegation_core/config.json` and your vault.

### Migrate a legacy ChromaDB index to SQLite

If you are upgrading from an installation that used `chroma.sqlite3`:

1. Install the migration extra if not already present: `pip install "delegation-core[chroma]"`.
2. Run the migration command shown in [Command line](reference/cli.md) or trigger a clean reindex into `indice.db`.
3. Verify counts and integrity with `delegation-core doctor`.

### Uninstall

Run the matching uninstaller script (`./uninstall.sh`, `uninstall.bat`, or `uninstall.command`). Your vault and downloaded model weights are never deleted.

## Ingest external folders

For recurring or shared document folders, declare them in `~/.delegation_core/config.json` under `ingest_sources` (see [INGEST_CONFIGURATION.md](INGEST_CONFIGURATION.md) for the full allow-list schema and exclusion rules).

Run configured sources:

```bash
delegation-core ingest --configured
```

Or ingest a single path via MCP (`ingest_folder` / `ingest_folder_bg`) or CLI. Re-runs are incremental: files whose `mtime` and size match both the registry and the index are skipped unless `force=True` is passed.

To remove a moved or deleted folder from both the index and registry, call `ingest_forget(source_path)`.

## Build and query a code graph

1. Ensure the graph extra is installed: `pip install -e ".[graph]"`.
2. Build a graph for a repository:
   - MCP: `graph_build_bg(repo_path="/path/to/repo", name="my-repo")`
   - Poll with `task_status(task_id)` until complete.
3. Inspect the result with `graph_report`, `graph_query`, `graph_node`, `graph_path`, or `graph_affected`.
4. Optionally install a git hook (`graph_hook_install`) to keep the graph current on commits.

## Enable or disable feature flags and scheduled tasks

Some MCP tools are gated behind configuration flags (see [Feature flags](reference/feature-flags.md) for the exact list and config keys). To toggle one:

1. Edit `~/.delegation_core/config.json` and set the corresponding boolean key.
2. Restart the daemon so the updated tool registry is exposed to clients.

Scheduled background tasks can be listed with `schedule_list()` and triggered on demand with `schedule_run(name)`.

## Diagnose and recover

1. **System check**:
   ```bash
   delegation-core doctor
   ```
   Reports Python/venv health, daemon reachability, index integrity, embedding model status, and client registrations.
2. **Inspect logs and alerts**:
   - Call `logs()` or `alerts()` via MCP, or check the log files under `~/.delegation_core/logs/`.
3. **Rebuild the search index**:
   - Trigger `vault_reindex_bg()` via MCP (or `delegation-core reindex` via CLI) if the index is out of sync with disk.
   - Because all notes live as plain Markdown files in your vault, rebuilding `indice.db` is non-destructive.
