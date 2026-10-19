# Declarative ingestion configuration

## Purpose

Use this configuration to turn recurring ingestion into an explicit policy:
which directories may enter the index and which parts must never be read. The
original files are never moved or modified; only extracted chunks are stored in
the local index.

Configure a source before its first ingestion when it is broad, shared,
recurring, or contains generated output. For a known one-off import, the direct
call remains available while `ingest_sources` is empty.

## Where to configure it

Edit the runtime `config.json`:

- Windows: `%USERPROFILE%\.delegation_core\config.json`
- Linux/macOS: `~/.delegation_core/config.json`

The file is strict JSON: do not add comments or a trailing comma. Back it up
before editing and restart the daemon after saving so it reloads the changes.

## Initial flow and later edits

For a first installation, run the installer and complete `setup` first. Edit
`config.json` only after that and before the first ingestion. Do not create the
file in advance: its presence can make the installer treat the machine as
already configured and skip the wizard. Upgrades preserve this file; review
sources only when paths or policy change.

For every later change:

1. Wait for any `ingest_configured_bg` job to finish and back up `config.json`.
2. Edit the source or patterns and validate the JSON syntax before saving.
3. Restart the daemon and start a new MCP client session to load the changed
   configuration and any updated tools.
4. Call `ingest_status` to check the declared source and its indexing history.
5. Call `ingest_configured` only when the index should be updated; saving the
   configuration never starts ingestion automatically.

To add a source, append an enabled entry and run it by name. To pause it, set
`"enabled": false`; that blocks future ingestion while retaining indexed content.
When a source path changes, call `ingest_forget` on the old path before removing
or changing its entry, then ingest the new path.

## Source path formats

Choose the format that matches the number of physical locations in one logical
source. Both are supported:

- Use **`path`** when a source has exactly one directory or file. This is the
  original format and remains fully supported.
- Use **`paths`** when one logical source must ingest two or more directories
  and/or files. Each item has one singular `path`, because it represents one
  physical location.

Do not put `path` and `paths` in the same source entry. Use the shorter `path`
form for one location; use `paths` as soon as the source needs multiple
locations.

### One physical location: `path`

```json
{
  "ingest_sources": [
    {
      "name": "project-docs",
      "path": "C:\\Example\\Projects\\project\\docs",
      "recursive": true,
      "enabled": true,
      "exclude": ["drafts/*"]
    }
  ]
}
```

### Multiple physical locations: `paths`

```json
{
  "ingest_sources": [
    {
      "name": "project-reference",
      "paths": [
        {
          "path": "C:\\Example\\Projects\\project\\docs",
          "recursive": true,
          "exclude": ["drafts/*"]
        },
        {
          "path": "C:\\Example\\Projects\\project\\README.md",
          "recursive": false
        },
        {
          "path": "C:\\Example\\Projects\\project\\AGENTS.md",
          "recursive": false
        }
      ],
      "enabled": true
    }
  ]
}
```

Running `delegation-core ingest --configured project-reference` ingests all
three physical paths, while keeping one logical source name for enabling,
disabling and reporting.

## Complete example

```json
{
  "ingest_sources": [
    {
      "name": "project-reference",
      "paths": [
        {
          "path": "C:\\Example\\Projects\\project\\docs",
          "recursive": true,
          "exclude": ["drafts/*"]
        },
        {
          "path": "C:\\Example\\Projects\\project\\README.md",
          "recursive": false
        }
      ],
      "enabled": true
    },
    {
      "name": "shared-docs",
      "path": "C:\\Example\\Shared\\reference-docs",
      "recursive": true,
      "enabled": false
    }
  ],

  "ingest_exclude_patterns": [
    ".git",
    "node_modules",
    "__pycache__",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    "*.log",
    "exports/private/*"
  ]
}
```

Each source requires either `path` or `paths`. A `name` is strongly recommended:
it identifies the logical source for `ingest --configured <name>`, reporting,
and enabling or disabling it. When omitted, the runtime falls back to the
physical path as its identifier. A `paths` array groups physical roots under one
logical source name; each item has its own optional `recursive` (default `true`)
and optional `exclude`. `enabled: false` keeps the entry as documentation but
prevents ingestion.

Use one source with multiple `paths` when the locations form one operational
unit, for example a documentation directory plus the repository `README.md`
and `AGENTS.md`. Use separate named sources when they should be run, paused or
forgotten independently.

## How rules are applied

`ingest_exclude_patterns` applies to every source. Source-level and per-path
`exclude` values, plus an `exclude` argument passed to a call, are additive;
none removes a global rule. A pattern can represent:

- A directory, such as `node_modules` or `.git`, which excludes its whole subtree.
- A filename or extension, such as `*.log` or `manifest.*`.
- A source-relative path, such as `exports/private/*` or `Logs/*`.

Without an explicit configuration, the defaults exclude Git metadata,
dependencies, caches, virtual environments, `dist`, `build`, coverage and test
output. Declare additional generated folders or text types that do not belong in
search. Defining `ingest_exclude_patterns` replaces the default list, so the
example repeats the directories that should remain protected.

When `ingest_sources` is empty, `ingest_folder` keeps its ad-hoc behavior: any
existing path can be provided. When at least one source is configured, a path
must exactly match a configured physical path. This makes the list an allow-list
and prevents an accidental ingestion of an entire `Projects` folder.

## Run configured ingestion

From the terminal:

```powershell
# All enabled sources
delegation-core ingest --configured

# One source by name
delegation-core ingest --configured project-docs

# Reprocess files even when size and modification time did not change
delegation-core ingest --configured project-docs --force
```

Through MCP, use `ingest_configured(name="project-docs")` for one source or
`ingest_configured()` for all sources. For large directories, use
`ingest_configured_bg` and track the returned `job_id` with `task_status`.

An existing `ingest_folder` call also respects global exclusions and, when its
path is registered, that source's exclusions.

## Change a rule after indexing

A new exclusion prevents future reads; it does not remove chunks already in the
index. To remove already indexed content, call `ingest_forget` for the physical
source path and then run configured ingestion again. For a logical source using
`paths`, call it once for each physical path that must be removed; the command
does not accept the logical source name. This removes only external-index rows
for that path and never deletes the original files.

Use `ingest_status` to inspect declared and indexed sources, counts and missing
paths. Disable a source to pause it, and call `ingest_forget` only when it must
also stop appearing in search results.

## Session transcript capture

Raw client transcripts can be stored locally in the vault `Sessions` folder by
a session-end hook. This is separate from the curated `export_session` note: a
transcript is a verbatim backup, while the curated note is the useful summary.
The hook redacts known credential-shaped values before it writes or indexes a
transcript, but redaction is a safety net, not a substitute for never sharing a
secret in a chat.

Configure the policy after installation in the same runtime `config.json`:

```json
{
  "session_transcripts": {
    "mode": "automatic"
  }
}
```

`automatic` is the default and preserves the existing behavior: each completed
supported-client session is written and then queued for reindexing. `manual`
saves only a session explicitly requested before it ends. `off` writes no raw
transcripts. Changing the mode never interrupts the local-model shutdown that
runs at session end.

To set the policy directly in `config.json`, keep the same structure and
replace the mode value as needed:

```json
{
  "session_transcripts": {
    "mode": "manual"
  }
}
```

```json
{
  "session_transcripts": {
    "mode": "off"
  }
}
```

### Client scope

The installer registers SessionStart and SessionEnd hooks for **Claude Code**
and **Codex**. At startup, each client receives a short vault-activity brief;
the Codex brief also directs the agent to the installed delegation-core-office skill.
At session end, both clients use the same local policy and store only their own
session transcripts. Codex provides the documented `session_id`, `cwd` and
`transcript_path` payload; the hook dispatches its export to a local worker so
Codex can close within its short SessionEnd timeout.

After installation or upgrade, restart **Codex**, review the new local hooks in
`~/.codex/hooks.json`, and allow them if Codex asks for a trust decision. This
is a Codex safety requirement; the installer never bypasses that review. The
installer also copies the `delegation-core` skill to
`~/.agents/skills/` without overwriting a same-named skill already owned by
the user. The other bundled skills are the Claude Code set and are not copied
there. Restart Codex after installation so it discovers the new skill.

The policy is checked before the Codex hook copies anything. With `off`, or with
`manual` and no pending request for Codex, no snapshot of the rollout is made and
the export worker never receives a transcript path. The local-model shutdown
still runs. A snapshot or payload left behind by a worker that never ran is
removed by the next Codex session end once it is a day old.

Open each VS Code session from an existing folder. Codex starts command hooks
with the session working directory, so a session still associated with a moved
or deleted folder cannot start a hook.

### Installing Codex after delegation-core

The installer writes the Codex hooks and the `delegation-core` skill whether or
not Codex is installed yet: `~/.codex/hooks.json` and `~/.agents/skills/` are
created if they are missing, and Codex reads them the first time it starts. Nothing
about the hooks has to be repeated when Codex arrives later. Two things are left:

1. Run `delegation-core clients --codex` to add the MCP server to
   `~/.codex/config.toml`. The hooks only talk to the vault; the tools come from
   that entry.
2. Start Codex and review the hooks with `/hooks` when it asks. Codex runs a
   command hook only after it is trusted, and the installer does not bypass that.

Codex 0.147.0 lists the `hooks` feature as stable and enabled (`codex features
list`). If `codex features list` shows it off in your version, turn it on before
looking for another cause.

### Windows PowerShell command helper

The installer runtime lives in a virtual environment. If `delegation-core` is
not available as a command in PowerShell, add the following function to your
PowerShell profile (`$PROFILE`). It provides the same short command for the
transcript-policy workflow without adding the virtual-environment directory to
the system `PATH`:

```powershell
function delegation-core {
    & "$env:USERPROFILE\.delegation_core\venv\Scripts\python.exe" -m delegation_core @args
}
```

Create the profile first when PowerShell reports that it does not exist:

```powershell
New-Item -ItemType File -Path $PROFILE -Force
```

Open a new PowerShell window after saving the function, or reload the current
profile with `. $PROFILE`. The function is local to the current Windows user
and applies to future PowerShell sessions.

Use these commands to manage the setting:

```powershell
# Inspect the active policy and whether a manual capture is pending
delegation-core session status

# Save no new raw transcripts
delegation-core session mode off

# Require explicit approval for the next session of one client
delegation-core session mode manual
delegation-core session capture-next --client codex

# Or authorize one Claude Code session, or the next session of either client
delegation-core session capture-next --client claude
delegation-core session capture-next --client any

# Restore the default automatic capture
delegation-core session mode automatic
```

`capture-next` creates a local, single-use marker for the selected client. The
next matching session that completes consumes it and is captured; if no matching
session starts, the marker remains pending and is visible in `session status`.
Use `--client any` only when either client may safely consume the authorization.
Restart the daemon and begin a new MCP client session after editing `config.json`
directly.

### Codex session end

Codex runs its SessionEnd hook when the root conversation ends. Use `/archive`
to close and archive a Codex conversation when a transcript must be captured
immediately. In some Codex clients, `/exit` only disconnects from the task; it
does not reliably end the conversation or trigger transcript capture.

### Claude Code in VS Code

The Claude Code terminal client emits its session-end event when its session exits.
The native Claude Code VS Code extension can keep its session active after a chat is
archived or closed; in practice, its session-end hook runs when the VS Code window
is closed. Use the integrated terminal and `/exit` when a transcript must be
captured immediately, or close VS Code to end the extension session.
