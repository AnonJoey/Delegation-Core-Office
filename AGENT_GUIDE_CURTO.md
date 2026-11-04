# delegation-core: short protocol

delegation-core is a local MCP server: a vector index over the user's markdown
vault, a persistent store, and (in `local` or `hybrid` mode) a local model.
Your job is judgment and synthesis. Its job is retrieval, compression and
persistence. Use it so you do not have to carry that work in your own context.

The complete reference is `~/.delegation_core/AGENT_GUIDE.md`. Do not load it
by default. Read the part you need when a tool surprises you.

## Start of session (silent)

1. `capabilities()` is the authority on what this server can do. This file and
   the long guide can be stale, the tool cannot.
2. `heartbeat()`. If `degraded`, tell the user and stop vault work. If
   `starting`, wait a few seconds and call it again without warning anyone.
3. `search_vault("<what the user just asked>")` before the first substantive
   answer. Cite the titles you used.

## While working

| Situation | Tool |
|-----------|------|
| Question that may have prior context | `search_vault` first |
| Long document, email or paste | `compress` (6000 chars per call), then reason |
| Decision made or confirmed | `write_note` to `Decisions` |
| Fix or workaround found | `write_note` to `Fixes` |
| Research finished | `write_note` to `Reference` |
| Follow-up on an existing topic | `vault_update_note`, never a duplicate note |
| Multi-step or multi-session task | `process_create`, then `process_update` |
| Large job (reindex, ingest, maintenance) | the `_bg` tool, then `task_status` |

Folder names come from `heartbeat()` under `vault.folder_counts`. Start a note
at its first heading: `write_note` adds the frontmatter.

## Rules

- Search results arrive as ranked `sources`. In `agent` and `hybrid` mode you
  write the answer. A summary marked as written by the local model is a lead,
  not a fact: check dates and numbers against the source before repeating them.
- Do not answer from memory when the vault may know better.
- Do not summarize a long input yourself. Compress it first.
- Do not read many notes one by one to build a summary. Search once.
- An error from a tool goes to the user. Do not hide it or retry in a loop.
- Never delete a note, an index folder or an index backup to make an error
  go away.

## End of session

On any goodbye or "we are done": `export_session(title, summary, key_decisions)`.
Confirm in one line.
