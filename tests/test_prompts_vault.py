"""Prompts MCP brief e ask."""

from __future__ import annotations

import json
import os
import time

from delegation_core import prompts_vault


def test_brief_junta_as_tres_fontes(tmp_path):
    cfgdir, vault = tmp_path / "c", tmp_path / "v"
    cfgdir.mkdir(); (vault / "Decisions").mkdir(parents=True)
    (cfgdir / "atencao.json").write_text(json.dumps({"itens": [
        {"tipo": "superseded", "texto": "`a.md` was updates by `b.md`", "dica": "dream_findings()"}]}))
    nova, velha = vault / "Decisions" / "nova.md", vault / "Decisions" / "velha.md"
    nova.write_text("x"); velha.write_text("y")
    antigo = time.time() - 30 * 86400
    os.utime(velha, (antigo, antigo))
    t = prompts_vault.brief(cfgdir, vault, {"active": [{"id": "p1", "name": "Merge", "steps_done": "1/3",
                                                       "updated": "2026-09-27"}]})
    assert "## Needs attention (1)" in t and "`a.md` was updates by `b.md`" in t
    assert "Merge (1/3 steps" in t and "Decisions/nova.md" in t and "velha" not in t


def test_brief_sem_nada(tmp_path):
    t = prompts_vault.brief(tmp_path, tmp_path, None)
    assert "## Needs attention (0)" in t and t.count("- none") == 2 and "- nothing" in t


def test_ask_manda_usar_ask_vault():
    t = prompts_vault.perguntar("qual porta?")
    assert "qual porta?" in t and "ask_vault" in t and "source_superseded_by" in t


def test_prompts_registrados():
    import asyncio
    import delegation_core.server as server
    nomes = {p.name for p in asyncio.run(server.mcp.list_prompts())}
    assert {"brief", "ask"} <= nomes
