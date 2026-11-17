from __future__ import annotations

import asyncio
import json

from delegation_core import disponibilidade
from delegation_core.config import Config


#: Porte do ai-memory (docs/ai-memory.md): nasce tudo desligado, e desligado a ferramenta nem aparece.
DESLIGADAS_POR_PADRAO = {"vault_forget_sweep", "vault_note_feedback", "handoff_create", "handoff_pickup", "handoff_list", "handoff_cancel"}


def test_padrao_esconde_a_busca_web_e_o_porte_do_ai_memory():
    assert set(disponibilidade.escondidas(Config(), tem_grafo=True)) == {"search_web"} | DESLIGADAS_POR_PADRAO


def test_ligar_as_chaves_do_porte_mostra_as_ferramentas():
    e = disponibilidade.escondidas(Config(envelhecimento_enabled=True, passagem_enabled=True), tem_grafo=True)
    assert set(e) == {"search_web"}
    desligado = disponibilidade.escondidas(Config(passagem_enabled=True), tem_grafo=True)
    assert "vault_forget_sweep" in desligado and "handoff_create" not in desligado
    assert "envelhecimento_enabled=false" in desligado["vault_forget_sweep"]["reason"]


def test_chaves_desligadas_e_extra_ausente():
    cfg = Config(sonho_enabled=False, web_search_enabled=True)
    e = disponibilidade.escondidas(cfg, tem_grafo=False)
    assert {"dream_run", "dream_apply", "graph_build", "graph_preview"} <= set(e)
    assert "search_web" not in e
    assert "sonho_enabled=false" in e["dream_run"]["reason"] and "[graph]" in e["graph_build"]["fix"]


def test_toda_ferramenta_citada_existe():
    from tests.test_escopos import _ferramentas
    todas = _ferramentas()
    citadas = {f for fs in disponibilidade.POR_CHAVE.values() for f in fs} | set(disponibilidade.EXTRA_GRAFO)
    assert citadas <= todas


def test_cliente_nao_ve_a_escondida_e_capabilities_explica(monkeypatch):
    from fastmcp import Client, FastMCP
    import delegation_core.server as server

    app = FastMCP("t")

    @app.tool()
    def search_web(query: str) -> str:
        return "x"

    @app.tool()
    def search_vault(query: str) -> str:
        return "y"
    ocultas = disponibilidade.aplicar(app, Config())

    async def roda():
        async with Client(app) as c:
            return [t.name for t in await c.list_tools()]
    assert asyncio.run(roda()) == ["search_vault"]
    assert set(ocultas) >= {"search_web"}

    monkeypatch.setattr(server, "_OCULTAS", ocultas)
    monkeypatch.setattr(server, "_vault", None)
    rel = json.loads(asyncio.run(server.capabilities()))
    assert "web_search_enabled" in rel["hidden_tools"]["search_web"]["reason"]
