---
name: delegation-core
description: Use delegation-core-office MCP tools to recover project context, retain useful decisions, and keep long coding sessions observable.
---

# delegation-core-office

Use the `delegation-core` MCP server provided by delegation-core-office as the
durable project-context layer.

## At the start of meaningful work

- Read the session briefing injected by the `SessionStart` hook.
- Search the vault when prior implementation decisions, runbooks, or project context would help.
- Do not treat a vault search as proof that a local service, repository state, or external system is currently healthy; verify the live state when it matters.

## During work

- Call `heartbeat` to confirm the service is healthy and to see the active processes. It takes no objective or status, only an optional `force` to bypass its cache.
- For work that spans sessions, track it with `process_create` and keep it current with `process_update`.
- Keep personal paths, names, tokens, credentials, and customer data out of notes and exported transcripts.
- Use the repository's documented engineering workflow for commits, tests, and pull requests; the skill does not authorize external writes or deployments.

## At handoff

- When the session produced reusable implementation knowledge, call `export_session` with a concise title, outcome, and the relevant repository/project context.
- The automatic session transcript policy is configured in delegation-core-office. In `manual` mode, a local operator must first run `delegation-core session capture-next --client <codex|claude>`, naming the client that is running; never assume a transcript was saved merely because an export was requested.
- Do not export raw transcripts if they could contain secrets or sensitive customer data. Prefer a concise, sanitized summary.
