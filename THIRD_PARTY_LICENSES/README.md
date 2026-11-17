# Third-party code

## Graphify (`src/delegation_core/graph/`)

`src/delegation_core/graph/` is vendored from [Graphify](https://github.com/Graphify-Labs/graphify),
Copyright 2026 Safi Shamsi and the Graphify contributors.

**Licensing is not a simple "your choice" dual license.** Upstream Graphify relicensed from MIT
to Apache License 2.0 on 2026-07-22 (its `0.9.25` release, one day before this project vendored
it): contributions made *before* the relicensing remain available under the original MIT terms,
per upstream's own `NOTICE` file, while the project as a whole is now Apache-2.0. All three
upstream files are reproduced verbatim here: `Graphify-LICENSE-Apache-2.0` (current primary
license), `Graphify-LICENSE-MIT` (retained terms for pre-relicense contributions), and
`Graphify-NOTICE` (upstream's own attribution notice, reproduced as required by the Apache
License's NOTICE-passthrough clause).

**What was taken:** the core pipeline (`detect`/`extract`/`build`/`cluster`/`analyze`/`report`/
`export`), all language extractors (`extractors/`, `exporters/`), the shared infrastructure
modules (`cache.py`, `dedup.py`, `ids.py`, `paths.py`, `resolver_registry.py`,
`pascal_resolution.py`, `ruby_resolution.py`, `security.py`, `validate.py`, `_minhash.py`), the
alternate-source ingesters (`google_workspace.py`, `manifest_ingest.py`, `mcp_ingest.py`), plus
(added 2026-07-23) `callflow_html.py` (Mermaid architecture diagrams), `affected.py`
(blast-radius query), and `wiki.py` (per-community/god-node articles) — 55 of Graphify's Python
files as vendored on 2026-07-23 (upstream's own tree has grown since; this list is not
recomputed against later upstream commits). Explicitly not included: Graphify's own CLI,
installer, LLM client, MCP server (`serve.py`), watch daemon, benchmark suite, "reflect"
memory-overlay system, and alternate ingestion sources (PR/query-log/SCIP/URL/video ingestion).
See `src/delegation_core/graph/__init__.py`'s module docstring for the authoritative list.

**Not vendored, but adapted (conceptually, not as source):** `src/delegation_core/graph_hook.py`
and `graph_hook_rebuild.py` reimplement the *idea* of Graphify's `hooks.py` (git post-commit hook
that keeps the graph fresh) using entirely original code, not a copy — those two upstream files
are built around Graphify's own uv-tool/pipx PATH-detection and a cross-repo lock/queue/drain
system that don't apply to delegation-core's single-venv install. No Graphify source was copied
into either file; see graph_hook.py's module docstring for the full rationale.

**Modifications made:** internal absolute imports (`graphify.xxx`) were rewritten to
`delegation_core.graph.xxx` to fit this project's package namespace; relative imports were left
unchanged. No other logic was altered. Per the Apache License's requirement to state significant
changes to modified files, this note constitutes that statement for the whole vendored tree rather
than a per-file changelog, since the change (namespace only) is mechanical and uniform.

Upstream: https://github.com/Graphify-Labs/graphify

## RTK (`src/delegation_core/filtros_saida/`)

The 62 filter definitions in `src/delegation_core/filtros_saida/rtk/*.toml` are copied verbatim
from [RTK](https://github.com/rtk-ai/rtk) (`src/filters/`, `develop` branch as downloaded on
2026-09-30), licensed under the Apache License 2.0, reproduced in `RTK-LICENSE-Apache-2.0`.
RTK ships no NOTICE file.

**Ported, not copied:** `filtros_saida/motor.py` and `filtros_saida/execucao.py` are Python
ports of RTK's Rust `src/core/toml_filter.rs`, the TOML fallback path of `src/main.rs`,
`src/core/tee.rs`, `src/core/retriever.rs` (sqlite mode) and `src/core/guard.rs`. The hook
rewrite in `filtros_saida/cli.py` follows the payload shape of `src/hooks/hook_cmd.rs` but never
returns a permission decision. Parity was measured against an RTK binary built from the same
source (`scripts/paridade_rtk.py`): 408 of 420 outputs identical, including recall hashes; the
12 others are commands RTK routes to dedicated Rust modules (`dotnet build`, `uv sync`).

**Command modules ported from Rust:** `filtros_saida/modulos/` ports RTK's `src/cmds/python/`
`mypy_cmd.rs`, `pytest_cmd.rs` and `ruff_cmd.rs`, and `src/cmds/git/` `git_cmd.rs` (status, add,
fetch, diff, log, show) and `gh_cmd.rs` (`gh pr`), and `src/cmds/system/` `search.rs` (`grep` and `rg`), `wc_cmd.rs` and `ls.rs`, together with the parts of `src/core/` they
use (`arg_tokenizer.rs`, `runner.rs`, `stream.rs` line handling, `guard.rs`). Parity is measured
against the same RTK binary (`scripts/paridade_rtk_modulos.py`, `paridade_rtk_git.py`,
`paridade_rtk_gh.py`, `paridade_rtk_busca.py`, `paridade_rtk_sistema.py`). The two git modules are partial: `rtk_modulos.json` lists what is ported.

## Headroom (`src/delegation_core/compressao/`)

[Headroom](https://github.com/headroomlabs-ai/headroom), Copyright 2025 Headroom Contributors,
Apache License 2.0 (`Headroom-LICENSE-Apache-2.0`; upstream `NOTICE` reproduced as
`Headroom-NOTICE`, as the license's NOTICE clause requires). Source: the `main` branch as
downloaded on 2026-09-30 (version string 0.39.1 plus unreleased changes).

**Copied verbatim:** `compressao/headroom_py/content_detector.py`,
`compressao/headroom_py/lossless_compaction.py`,
`compressao/headroom_py/transforms/cross_turn_dedup.py` and
`compressao/headroom_py/transforms/read_lifecycle.py`, from `headroom/transforms/`. A test checks
they are byte-identical to the downloaded copy when it is present. `proxy/dedup.py` adapts
`ContentRouter._cross_turn_dedup_messages` (same file of upstream) to the proxy; a differential test runs the
original over 250 random conversations (`tests/test_proxy_dedup.py`), and `proxy/leitura.py` wires
`read_lifecycle` to the delegation-core CCR store (400 conversations, `tests/test_proxy_leitura.py`).

**Ported from Rust, not copied:** `compressao/logs.py`, `diff.py`, `busca.py`, `adaptativo.py`
and `sinais.py` port `crates/headroom-core/src/transforms/{log_compressor,diff_compressor,
search_compressor,adaptive_sizer}.rs` and `src/signals/keyword_detector.rs`. In Headroom's
published package these algorithms live in a compiled Rust module; parity was measured
against that module built from the same source (`scripts/paridade_headroom.py`): diff and
search identical on every input tested; log identical except where the Rust code validates
its cut with miniz_oxide and the port with zlib, which compress to slightly different sizes.

**Kompress (added 2026-10-05):** `compressao/headroom_py/transforms/kompress_compressor.py`,
`transforms/base.py` and `onnx_runtime.py` are copied verbatim, keeping Headroom's layout so their
relative imports resolve. The modules they import from the rest of Headroom (`config`, `tokenizer`,
`cache/compression_store`, `telemetry`) are small replacements written for delegation-core: the
compression store writes to delegation-core's CCR store, and telemetry is a no-op that records and
sends nothing. The model itself (`chopratejas/kompress-v2-base` on Hugging Face) is not
redistributed; `delegation-core kompress setup` downloads it to the local Hugging Face cache.

**SmartCrusher (added 2026-10-05):** `compressao/smartcrusher/` ports
`crates/headroom-core/src/transforms/smart_crusher/` (analyzer, planner, crushers, constraints,
the lossless compaction stage with its three formatters, and the document walker) and the
anchor selector and BM25 relevance scorer it uses. Ported from Rust, not copied. Parity measured
against the core built from the same source (`scripts/paridade_smartcrusher.py`): identical
output, strategy string and modified flag on every input tested, in eight configurations.
`tests/fixtures/smartcrusher/oraculo.json.gz` holds outputs recorded from that core.

**Not taken:** providers, memory, learn, dashboard, telemetry and the code-aware (AST) compressor.

## ai-memory (`src/delegation_core/{envelhecimento,resumo_inicial,passagem}/`, `ranqueamento/autoridade.py`)

[ai-memory](https://github.com/akitaonrails/ai-memory), Copyright (c) 2026 Fabio Akita, MIT License
(`ai-memory-LICENSE-MIT`). Source: revision `584ab792` (2026-10-16, version 3.1.0). Nothing is copied
into the Python package; every module is a **port from Rust**:

| Python | Rust (`crates/`) |
|---|---|
| `envelhecimento/retencao.py` | `ai-memory-store/src/decay.rs` |
| `envelhecimento/fatos_duraveis.py` | `ai-memory-consolidate/src/keep_tokens.rs` |
| `envelhecimento/compactacao.py` | `ai-memory-consolidate/src/compaction.rs` |
| `envelhecimento/varredura.py` | `ai-memory-consolidate/src/sweep.rs` (`is_decayable`, `cold_entry_for`, order of the passes) |
| `resumo_inicial/trecho.py` | `ai-memory-core/src/excerpt.rs`, `profile.rs` (`is_metadata_field`) |
| `resumo_inicial/niveis.py` | `ai-memory-hooks/src/brief_tiers.rs` |
| `ranqueamento/autoridade.py` | `ai-memory-store/src/reader.rs` (`PageAuthority`, `apply_rank_multiplier`, `authority_candidate_limit`), `retrieval_tuning.rs` (`is_session_recall_query`) |
| `passagem/caminhos.py`, `passagem/armazem.py` | `ai-memory-store/src/reader.rs`, `ops.rs`, `writer.rs` (handoff selection, accept, expire) |
| `passagem/texto.py`, `cerca_nao_confiavel.py` | `ai-memory-hooks/src/router.rs` (`render_handoff_markdown`, `render_handoff_notice`, `escape_untrusted_history`) |

Parity is measured against the Rust functions compiled from the same revision
(`scripts/oraculo_ai_memory`, `scripts/paridade_ai_memory.py`). The oracle copies those functions
**verbatim** (each file header cites file, lines and revision); it is a test tool and is not part of
the installed package. `texto_alfabetico.py` is generated from the oracle's `char::is_alphabetic`.

**Not taken:** the SQLite/FTS5 retrieval stack, the Rust MCP server, workstreams, the auto-improve
loop, cold-cluster DBSCAN dedup, observation and ledger pruning, the cross-project profile and
the hook installers. See `docs/ai-memory.md`.
