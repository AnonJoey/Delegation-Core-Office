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

- Windows: `%USERPROFILE%\\.delegation_core\\config.json`
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
