"""Livro-caixa: o agregado, o middleware e a ferramenta."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import livro_mcp
from delegation_core.livro import LivroCaixa


@pytest.fixture
def lv(tmp_path):
    x = LivroCaixa(tmp_path / "l.sqlite3")
    yield x
    x.fechar()


def test_relatorio_agrega_por_ferramenta(lv):
    for s in (0.1, 0.2, 0.3, 10.0):
        lv.registrar("search_vault", s, 50, 4000, cliente="claude-code", chars_apontados=20000, em=100)
    lv.registrar("compress", 2.0, 6000, 800, cliente="desktop", erro="unavailable", em=100)
    r = lv.relatorio()
    sv = next(f for f in r["ferramentas"] if f["ferramenta"] == "search_vault")
    assert sv["chamadas"] == 4 and sv["segundos_p50"] == 0.25 and sv["segundos_p95"] == 10.0
    assert sv["chars_saida"] == 16000 and sv["erros"] == 0
    assert next(f for f in r["ferramentas"] if f["ferramenta"] == "compress")["erros"] == 1
    assert r["clientes"] == {"claude-code": 4, "desktop": 1}
    assert r["tokens_entregues_estimados"] == (16000 + 800) // 4
    assert r["tokens_apontados_teto"] == 80000 // 4


def test_relatorio_respeita_desde(lv):
    lv.registrar("a", 1, 1, 1, em=10)
    lv.registrar("b", 1, 1, 1, em=20)
    assert [f["ferramenta"] for f in lv.relatorio(desde=15)["ferramentas"]] == ["b"]


def test_chars_apontados_soma_as_notas_das_fontes(tmp_path):
    (tmp_path / "Fixes").mkdir()
    (tmp_path / "Fixes" / "a.md").write_text("x" * 300)
    cfg = SimpleNamespace(vault=tmp_path)
    texto = json.dumps({"sources": [{"path": "Fixes/a.md"}, {"path": "sumiu.md"}, {"sem": "path"}]})
    assert livro_mcp.chars_apontados(cfg, texto) == 300
    assert livro_mcp.chars_apontados(cfg, "nao e json") == 0
    assert livro_mcp.chars_apontados(cfg, "[1, 2]") == 0


class _Ctx:
    def __init__(self, nome, args, cliente="claude-code"):
        self.message = SimpleNamespace(name=nome, arguments=args)
        info = SimpleNamespace(name=cliente)
        self.fastmcp_context = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(clientInfo=info)))


def _res(texto):
    return SimpleNamespace(content=[SimpleNamespace(text=texto)])


def test_middleware_lanca_sucesso_erro_tipado_e_excecao(tmp_path):
    cfg = SimpleNamespace(vault=tmp_path, livro_enabled=True, livro_path=str(tmp_path / "l.sqlite3"))
    livro_mcp._LIVROS.clear()
    mw = livro_mcp.LivroMiddleware(cfg)

    async def ok(ctx):
        return _res(json.dumps({"x": 1}))

    async def tipado(ctx):
        return _res(json.dumps({"error": "nao achei", "error_type": "not_found"}))

    async def quebra(ctx):
        raise RuntimeError("boom")

    asyncio.run(mw.on_call_tool(_Ctx("a", {"q": "oi"}), ok))
    asyncio.run(mw.on_call_tool(_Ctx("b", {}), tipado))
    with pytest.raises(RuntimeError):
        asyncio.run(mw.on_call_tool(_Ctx("c", {}), quebra))
    r = {f["ferramenta"]: f for f in livro_mcp.livro(cfg).relatorio()["ferramentas"]}
    assert r["a"]["erros"] == 0 and r["a"]["chars_entrada"] == len('{"q": "oi"}')
    assert r["b"]["erros"] == 1 and r["c"]["erros"] == 1
    assert livro_mcp.livro(cfg).relatorio()["clientes"] == {"claude-code": 3}
    livro_mcp._LIVROS.clear()


def test_middleware_nunca_derruba_a_chamada(tmp_path, monkeypatch):
    cfg = SimpleNamespace(vault=tmp_path, livro_enabled=True, livro_path=str(tmp_path / "l.sqlite3"))
    monkeypatch.setattr(livro_mcp, "livro", lambda c: (_ for _ in ()).throw(OSError("disco")))

    async def ok(ctx):
        return _res("{}")
    assert asyncio.run(livro_mcp.LivroMiddleware(cfg).on_call_tool(_Ctx("a", {}), ok)).content[0].text == "{}"


def test_usage_report_e_desligado(tmp_path, monkeypatch):
    cfg = SimpleNamespace(vault=tmp_path, livro_enabled=True, livro_path=str(tmp_path / "l.sqlite3"))
    livro_mcp._LIVROS.clear()
    livro_mcp.livro(cfg).registrar("x", 1, 1, 1)
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=cfg))
    assert json.loads(server.usage_report())["chamadas"] == 1
    cfg.livro_enabled = False
    assert json.loads(server.usage_report())["error_type"] == "disabled"
    livro_mcp._LIVROS.clear()
