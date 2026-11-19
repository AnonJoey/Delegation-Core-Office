# Operations and Security

## Data residency: what stays local vs. what leaves the machine

- **Local by default**: the Obsidian vault, SQLite vector/lexical index (`indice.db`), BGE embeddings, ingestion registry (`~/.delegation_core/ingested_sources.json`), logs, and optional `llama.cpp` inference all run locally on your machine.
- **Network traffic only when explicitly triggered**:
  - Model downloads from Hugging Face during initial setup (`delegation-core setup`) or when fetching embeddings/models.
  - Self-updates from GitHub when you run `delegation-core update`.
  - Opt-in web search (`[web]` extra + `web_search_enabled=true`).
  - Any external MCP client (such as Claude or Gemini) naturally receives the tool responses returned to it during your session.

## Loopback binding, tokens, and secrets

- The HTTP daemon binds to `127.0.0.1` (loopback only). Do not expose the daemon port directly to a public network.
- Per-client bearer tokens are stored in `~/.delegation_core/` and written into client configurations by `delegation-core clients`.
- Session transcript export (`hooks/session_export.py`) redacts known credential shapes before writing raw transcripts into `Sessions/`, but you should still rotate any secret that was pasted into a terminal session.
- Agent session roots (`~/.claude/projects`, `~/.codex/sessions`) are skipped by default during external folder ingestion unless explicitly listed in `ingest_sources`, preventing raw session dumps from polluting the index.

## Files written on disk

- **`~/.delegation_core/`**: `config.json`, `ingested_sources.json`, client tokens, SQLite index (`indice.db`), local task/process state, and logs.
- **Vault directory**: plain Markdown notes, `_inbox/`, `Sessions/` transcripts (when enabled), and generated code-graph articles under `Reference/graphs/` (when `graph_build` is used).

## Known limitations and OS notes

- **`vault_dead_refs`**: currently parses POSIX-style paths only; Windows drive-letter paths in notes are not validated as dead references.
- **Windows consoles and WDAC**: background hooks and scheduled tasks use non-console launchers (`pythonw` / `CREATE_NO_WINDOW`) to avoid spawning visible terminal windows; environments with strict WDAC policies may require allow-listing the venv Python executable.
- **macOS (Apple Silicon)**: local embeddings and `llama.cpp` can use Metal acceleration; see [INSTALL_MAC_MLX.md](INSTALL_MAC_MLX.md) for macOS-specific notes.
- **Cross-machine vaults**: if the same vault is synced across Linux, macOS, and Windows, absolute local paths written in notes from one machine will appear as missing paths on another; do not bulk-delete dead references without checking machine origin.

For the full list of environment variables and error codes, see [Environment variables](reference/environment.md) and [Errors a tool can return](reference/errors.md).
