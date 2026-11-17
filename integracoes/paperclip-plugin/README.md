# delegation-core memory for Paperclip

A Paperclip plugin (alpha SDK) that makes a delegation-core daemon the memory of
a Paperclip company. It maps to the `memory_*` MCP tools, which follow the
`MemoryAdapter` contract from Paperclip's own memory plan
(`doc/plans/2026-03-17-memory-service-surface-api.md` in their repository).

**Status: skeleton, not tested against a running Paperclip.** The shapes come
from Paperclip's plugin spec and its kitchen-sink example at v2026.1001.0; the
daemon side (`memory_*` tools) is covered by `tests/test_adaptador_paperclip.py`.

## What it adds

| Agent tool | delegation-core call | Notes |
|---|---|---|
| `delegation-core.memory:recall` | `memory_query` | scope = company, agent and project of the run |
| `delegation-core.memory:remember` | `memory_upsert` | `agentOnly` keeps it to this agent |
| event `agent.run.finished` | `memory_capture` | residue of each run, when `captureRuns` is on |

`memory_forget` is deliberately not exposed to agents: it is in the
`destructive` class, which the daemon can put behind a human approval
(`delegation-core policy set paperclip destructive require_approval`).

## Setup

1. On the machine running delegation-core: `delegation-core token create paperclip --write`.
2. Make the daemon reachable from the Paperclip server. It binds `127.0.0.1`
   by default; a Paperclip instance on a VPS cannot reach a laptop without a
   tunnel. This is the step to measure first.
3. In Paperclip: store the token as a secret, install this plugin by local path
   (`pnpm build`, then `paperclipai plugin install <path>`), and fill
   `daemonUrl` and `tokenSecretRef` in its settings.

Records land in the vault at `Reference/paperclip/<companyId>/`
(`paperclip_memory_folder` in the daemon config), as ordinary notes.
