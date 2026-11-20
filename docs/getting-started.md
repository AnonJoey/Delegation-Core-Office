# Getting Started

Delegation-Core Office is a local MCP server and CLI that gives AI coding agents shared access to an Obsidian-compatible Markdown vault, a SQLite vector/lexical search index (BGE embeddings + exact numpy cosine similarity + FTS5), an optional local LLM (`llama.cpp`), and a vendored code-graph pipeline.

All clients on the machine connect to a single HTTP daemon (`127.0.0.1:8797` by default), so embeddings, the index, and any local model are loaded once per machine rather than once per client.

## What it is, and what it is not

- **It is** a local memory, retrieval, ingestion, and automation layer shared across Claude Code, Claude Desktop, Antigravity, Codex, Cursor, OpenCode, and Grok.
- **It is not** a cloud service or a SaaS sync backend. Everything stays on disk under your Obsidian vault and `~/.delegation_core/` unless you explicitly enable opt-in features such as web search (`[web]`).

## Installation

### Platform installer (recommended)

The platform installer detects Python (`>=3.11`), creates a dedicated virtual environment, installs `delegation-core`, installs the native Tauri dashboard when available, and runs the interactive setup wizard on first install. Re-running it on an existing install upgrades in place while preserving `~/.delegation_core/config.json`.

```bash
# Linux / macOS
./install.sh

# Windows
install.bat
```

On macOS, `install.command` is a double-clickable Finder wrapper for `install.sh`.

To uninstall cleanly (venv, config, logs, hooks) without touching your vault or downloaded model weights, run `uninstall.sh`, `uninstall.bat`, or `uninstall.command`.

### Manual / developer install

```bash
pip install -e .             # Core: vault, SQLite index, MCP daemon, CLI
pip install -e ".[graph]"    # Optional: tree-sitter code-graph pipeline
pip install -e ".[web]"      # Optional: DuckDuckGo web search
pip install -e ".[chroma]"   # Optional: read legacy ChromaDB indexes for migration
pip install -e ".[dev]"      # Optional: pytest and test dependencies
```

## First-time setup

Run the setup wizard once per machine:

```bash
delegation-core setup
```

The wizard lets you:

1. Point to an existing Obsidian vault or create a new one.
2. Choose an engine mode (`agent`, `local`, or `hybrid`) and optionally configure a local `llama.cpp` model.
3. Optionally register the daemon to start automatically (systemd on Linux, launchd on macOS, Task Scheduler on Windows).

Verify the installation at any time:

```bash
delegation-core doctor
```

## Connecting MCP clients

Write the HTTP daemon entry and bearer token into all detected clients:

```bash
delegation-core clients
```

The daemon listens on `127.0.0.1:8797` by default (chosen to avoid colliding with Headroom's `8787` proxy port). Existing installations keep their configured `server_port` in `~/.delegation_core/config.json`.

> **Upgrading from v0.10 or earlier (stdio):** remove any leftover `{"command": ..., "args": ["run"]}` stdio entries so clients do not spawn competing server processes against the daemon.

## First search

Once the daemon is running and your client is connected:

1. Call `capabilities()` to inspect the live set of registered MCP tools.
2. Call `search_vault(query="...")` to search your vault semantically.
3. Run `delegation-core status` from the terminal to check daemon health, index counts, and connected clients.

## Next steps

- Understand the architecture and engine modes: [Concepts](concepts.md)
- Day-to-day operational tasks: [Guides](guides.md)
- Complete auto-generated reference (tools, config keys, CLI, routes, errors): [Reference](reference/README.md)
