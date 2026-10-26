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

## When the service or the index misbehaves

- Diagnose with `heartbeat` and `delegation-core doctor`; each failing check prints a remedy. Measure the cause before naming it.
- `starting` in `heartbeat` is normal for up to about a minute after the daemon comes up. Wait and call it again.
- Only the daemon may hold the index open. Anything that writes to it (`doctor --rebuild-fts`, `doctor --clean-orphans`, `recover-index`, `index-migrate`) needs `delegation-core service stop` first and `service start` after. Do not bypass a refusal with `--force`.
- Never delete an index folder, an index backup, or a vault note to clear an error, and do not edit the installed package: a code defect is reported, not patched.
- Ask the user before restarting the daemon or deleting anything. After two failed attempts, stop and report.
- The full symptom table and the reporting format are in the `AGENT_GUIDE.md` section "When something on this machine is wrong".
