"""Aba Vigia do painel: o estado lido dos arquivos, o rodar agora, e as rotas da API."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import livro_mcp, painel_vigia, sonho_vault


@pytest.fixture
def base(tmp_path, monkeypatch):
    (tmp_path / "alertas.json").write_text(json.dumps({
        "alertas": {"a": {"estado": "disparando", "mensagem": "12 links quebrados", "severidade": "aviso"},
                    "b": {"estado": "pendente", "mensagem": "ainda nao"}},
        "eventos": [{"tipo": "aberto", "n": i} for i in range(30)], "avaliado_em": 123.0}))
    (tmp_path / "agenda.json").write_text(json.dumps({"alertas": {"execucoes": 2, "ultimo_status": "ok"}}))
    cfg = SimpleNamespace(recordacao_enabled=True, recordacao_path=str(tmp_path / "rec.sqlite3"),
                          livro_enabled=True, livro_path=str(tmp_path / "livro.sqlite3"))
    monkeypatch.setattr(server, "_vigia", None)
    sonho_vault._REGISTRO.clear()
    livro_mcp._LIVROS.clear()
    yield SimpleNamespace(cfg=cfg, dir=tmp_path)
    sonho_vault._REGISTRO.clear()
    livro_mcp._LIVROS.clear()


def test_estado_le_os_arquivos(base):
    sonho_vault.registro(base.cfg).registrar("q", ["a.md"])
    livro_mcp.livro(base.cfg).registrar("search_vault", 0.2, 10, 100)
    e = painel_vigia.estado(base.cfg, base.dir)
    assert [a["mensagem"] for a in e["alertas"]["abertos"]] == ["12 links quebrados"]
    assert len(e["alertas"]["eventos"]) == 20 and e["alertas"]["eventos"][0]["n"] == 29
    assert e["agenda"] == {"tarefas": [{"nome": "alertas", "execucoes": 2, "ultimo_status": "ok"}], "ao_vivo": False}
    assert e["recordacao"]["totais"]["consultas"] == 1 and e["uso"]["chamadas"] == 1
    assert e["atencao"] == {"itens": [], "gerado_em": None, "erros": {}}


def test_estado_traz_o_atencao_json(base):
    item = {"chave": "k", "tipo": "superseded", "texto": "`a` was updates by `b`", "dica": "dream_findings()"}
    (base.dir / "atencao.json").write_text(json.dumps({"gerado_em": 5.0, "itens": [item], "erros": {"x": "y"}}))
    e = painel_vigia.estado(base.cfg, base.dir)
    assert e["atencao"] == {"itens": [item], "gerado_em": 5.0, "erros": {"x": "y"}}


def test_estado_sem_nada_nao_quebra(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_vigia", None)
    cfg = SimpleNamespace(recordacao_enabled=False, livro_enabled=False)
    e = painel_vigia.estado(cfg, tmp_path)
    assert e["alertas"]["abertos"] == [] and e["agenda"]["tarefas"] == [] and e["recordacao"] is None


def test_com_vigia_vivo_a_agenda_vem_dele_e_roda(base, monkeypatch):
    vivo = SimpleNamespace(agenda=SimpleNamespace(proximas=lambda: [{"nome": "x", "proxima": "amanha"}]),
                           rodar=lambda nome: {"ultimo_status": "ok", "nome": nome})
    monkeypatch.setattr(server, "_vigia", vivo)
    e = painel_vigia.estado(base.cfg, base.dir)
    assert e["agenda"] == {"tarefas": [{"nome": "x", "proxima": "amanha"}], "ao_vivo": True}
    assert painel_vigia.rodar("x") == {"ultimo_status": "ok", "nome": "x"}


def test_rodar_sem_daemon_explica(base):
    assert "inside the daemon" in painel_vigia.rodar("x")["error"]


def test_rotas_da_api_existem_nas_duas_pontas():
    """O contrato do painel: o que o main.js pede, a API atende."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    js = (raiz / "dashboard" / "src" / "main.js").read_text(encoding="utf-8")
    api = (raiz / "src" / "delegation_core" / "dashboard_api.py").read_text(encoding="utf-8")
    for rota in ("/api/vigia", "/api/vigia/run"):
        assert f'"{rota}"' in js and f'"{rota}"' in api
