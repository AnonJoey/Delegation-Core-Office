"""completion/complete pelos prompts: chega pelo protocolo, sai do estado atual."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import completar
from delegation_core.tracker import ProcessTracker


@pytest.fixture
def estado(tmp_path, monkeypatch):
    raiz = tmp_path / "vault"
    (raiz / "Decisions" / "sub").mkdir(parents=True)
    for n in ("Deploy da Acme", "deploy antigo", "Orçamento"):
        (raiz / "Decisions" / f"{n}.md").write_text("x")
    (raiz / "Decisions" / "sub" / "Décima nota.md").write_text("x")
    (raiz / "Decisions" / ".oculta").mkdir()
    (raiz / "Decisions" / ".oculta" / "deploy secreto.md").write_text("x")
    cfg = SimpleNamespace(vault=raiz, vault_folders=["Decisions"])
    tr = ProcessTracker(tmp_path / "p.json")
    tr.create("Migrar busca")
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=cfg))
    monkeypatch.setattr(server, "_tracker", tr)
    return cfg, tr


def test_filtro_prefixo_sem_caixa_e_ordenado():
    assert completar.filtrar(["b", "Ab", "ab", "ab", "c"], "A") == (["Ab", "ab"], False)
    assert completar.filtrar(["Orçamento"], "ORÇ") == (["Orçamento"], False)


def test_pelo_protocolo(estado):
    from fastmcp import Client
    from mcp.types import PromptReference

    async def roda():
        async with Client(server.mcp) as c:
            nomes = {p.name for p in await c.list_prompts()}
            notas = await c.complete(PromptReference(type="ref/prompt", name="review_note"),
                                     {"name": "note", "value": "dep"})
            proc = await c.complete(PromptReference(type="ref/prompt", name="continue_process"),
                                    {"name": "process_id", "value": "migr"})
            nada = await c.complete(PromptReference(type="ref/prompt", name="review_note"),
                                    {"name": "argumento_qualquer", "value": ""})
            return nomes, notas, proc, nada
    nomes, notas, proc, nada = asyncio.run(roda())
    assert {"review_note", "continue_process", "investigate_question"} <= nomes
    assert notas.values == ["Deploy da Acme", "deploy antigo"], "a pasta oculta fica de fora"
    assert proc.values == ["Migrar busca"]
    assert nada.values == []


def test_erro_na_fonte_vira_lista_vazia(monkeypatch):
    def quebra(*a):
        raise RuntimeError("x")
    monkeypatch.setattr(completar, "candidatos", quebra)
    assert completar.completar("note", "a", None, None) == ([], False)
