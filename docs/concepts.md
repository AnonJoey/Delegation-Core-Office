# Concepts

This page explains how Delegation-Core Office organizes knowledge, executes searches, and coordinates work across clients. For exact parameter lists, configuration keys, and tool names, see the generated [Reference](reference/README.md).

## Vault and folders

Your Obsidian vault remains plain Markdown files on disk. Delegation-Core reads and writes notes in standard folders (such as `Projects/`, `Decisions/`, `Infrastructure/`, `Procedures/`, `Fixes/`, `Reference/`, `Sessions/`) and watches `_inbox/` for raw files that can be classified, synthesized, and filed.

Every write keeps a history snapshot so notes can be inspected (`vault_note_history`, `vault_note_diff`) and restored (`vault_note_restore`).

## Search index and scopes

Delegation-Core stores embeddings and metadata in a single SQLite file (`indice.db`) using exact cosine similarity in NumPy paired with lexical matching (FTS5) for hybrid retrieval. ChromaDB is no longer a required dependency; it is only needed via the `[chroma]` extra to migrate legacy indexes.

`search_vault` supports explicit **scopes** (`scope` parameter) to prevent machine-generated articles from drowning out hand-written notes:

- `notes`: hand-written vault notes only.
- `external`: files indexed via `ingest_folder` / `ingest_configured`.
- `generated`: code-graph wiki articles produced by `graph_build`.
- `notes+external`: hand-written notes and ingested external files (excluding generated graph articles).
- `all`: everything in the index.

When `client_path_roots` is configured, searches can also be narrowed with `client="<name>"` to avoid cross-client leakage.

## Engine modes (`local`, `agent`, `hybrid`)

Delegation-Core supports three engine modes (see `engine_mode` in [Configuration keys](reference/config.md)):

- **`agent`**: retrieval runs locally with BGE embeddings, and ranked snippets are returned directly to the calling LLM agent for synthesis. No local LLM is loaded.
- **`local`**: a local `llama.cpp` server summarizes and synthesizes answers locally.
- **`hybrid`**: defaults to `agent` mode for speed, with opt-in local synthesis (`use_local=true`).

## Single HTTP daemon, tokens, and permissions

One background daemon serves all MCP clients over HTTP on loopback (`127.0.0.1`). Each client receives a per-client bearer token and permission scope managed in `~/.delegation_core/`, preventing multiple processes from fighting over the SQLite index or GPU memory.

## Maintenance, schedules, alerts, and memory

- **Scheduled tasks** (`agenda/`): background jobs for maintenance, inbox processing, transcript digestion, and periodic health checks. See [Scheduled tasks](reference/schedule.md).
- **Alerts** (`alertas/`): rule-based checks surfaced at session start (`alerts`, `alerts_check`). See [Alert rules](reference/alerts.md).
- **Dreaming & facts**: periodic consolidation extracts durable facts (`vault_facts`), detects stale or conflicting notes (`dream_run`, `dream_findings`), and applies approved updates (`dream_apply`).
- **Paperclip memory & governance**: structured memory entries (`memory_capture`, `memory_upsert`, `memory_query`), approval queues (`approval_list`), and tool policies (`tool_policy`).

## Output filtering, compression, and proxy

- **Output filtering (`filter_output`) & compression (`compress_output`)**: trim verbose command output before it consumes the agent's context window while preserving the raw original for exact recovery (`recall_output`).
- **Context pruning (`cores_prune_context`)**: pattern-based context pruning with recoverable originals.

## Code graphs

When installed with `pip install -e ".[graph]"`, Delegation-Core runs a vendored AST pipeline (adapted from Graphify) across tree-sitter languages to build `graph.json`, interactive HTML views (`graph.html`, `callflow.html`), `GRAPH_REPORT.md`, and per-community wiki articles. Graph tools (`graph_query`, `graph_node`, `graph_path`, `graph_affected`, `graph_notes`) link code entities directly to vault notes.

## Cores and workflow tracking

- **Cores** (`src/delegation_core/cores/`): modular capabilities exposed as MCP tools — local skills search (`cores_skills_search`), prompt sanitization (`cores_sanitize_prompt`), document-to-Markdown conversion (`cores_multimodal_ingest`), context pruning (`cores_prune_context`), and a static self-hosted service catalog (`cores_selfhosted_catalog`).
- **Cross-session coordination**: lightweight processes (`process_create`, `process_claim`, `process_update`), open questions (`question_record`, `question_resolve`), status cards (`status_card_save`, `standup`), and declarative shell DAG workflows (`dag_run`, `dag_status`).
