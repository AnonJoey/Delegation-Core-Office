# Delegation-Core Office

A local MCP server and CLI that gives AI coding agents shared access to an Obsidian-compatible Markdown vault, a SQLite vector/lexical search index (BGE embeddings + exact numpy search + FTS5), an optional local LLM (`llama.cpp`), and a vendored code-graph pipeline.

It runs as a single HTTP daemon (`127.0.0.1:8797` by default) shared by every client on the machine — Claude Code, Claude Desktop, Antigravity, Codex, Cursor, OpenCode, and Grok — so embeddings, the index, and any local model are loaded once per machine rather than once per client.

## Quick install

```bash
./install.sh          # Linux / macOS (or double-click install.command on macOS)
install.bat           # Windows
```

For manual/developer installs:

```bash
pip install -e .             # core (vault, SQLite index, MCP daemon, CLI)
pip install -e ".[graph]"    # + tree-sitter code-graph pipeline
pip install -e ".[web]"      # + opt-in DuckDuckGo web search
pip install -e ".[dev]"      # + pytest
```

Then run the one-time setup wizard and register your MCP clients:

```bash
delegation-core setup
delegation-core clients
delegation-core doctor
```

## Documentation

- **[Getting Started](docs/getting-started.md)** — installation, setup wizard, connecting MCP clients, first search
- **[Concepts](docs/concepts.md)** — vault, SQLite index and search scopes, engine modes (`agent` / `local` / `hybrid`), daemon, memory, filters, code graphs, cores
- **[Guides](docs/guides.md)** — updating, migrating from ChromaDB, external folder ingestion, building code graphs, feature flags, troubleshooting
- **[Operations and Security](docs/operations-and-security.md)** — data residency, tokens, files on disk, OS notes and known limitations
- **[Development](docs/development.md)** — repository layout, running tests, regenerating reference docs, CI and releases
- **[Generated Reference](docs/reference/README.md)** — auto-generated from code and verified by tests:
  - [MCP tools](docs/reference/tools.md) | [Feature flags](docs/reference/feature-flags.md) | [Configuration keys](docs/reference/config.md)
  - [CLI commands](docs/reference/cli.md) | [Dashboard HTTP API](docs/reference/dashboard-api.md) | [Environment variables](docs/reference/environment.md)
  - [Scheduled tasks](docs/reference/schedule.md) | [Alert rules](docs/reference/alerts.md) | [Tool errors](docs/reference/errors.md)
- **[Agent Protocol](AGENT_GUIDE.md)** — operational protocol copied to connected AI agents (`AGENT_GUIDE_CURTO.md` for concise clients)

## License & third-party notices

See `LICENSE` and `THIRD_PARTY_LICENSES/` (includes the vendored code-graph pipeline adapted from [Graphify](https://github.com/Graphify-Labs/graphify)).
