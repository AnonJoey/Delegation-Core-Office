from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import avaliacao, feedback_busca


def test_votar_relatorio_e_export(tmp_path):
    feedback_busca.votar("deploy porta", "Fixes/deploy.md", 1)
    feedback_busca.votar("Deploy porta", "Fixes/deploy.md", 1)
    feedback_busca.votar("deploy porta", "Sessions/x.md", -1)
    feedback_busca.votar("quem e o contato", "Sessions/x.md", -1)
    with pytest.raises(ValueError):
        feedback_busca.votar("q", "p", 0)
    r = feedback_busca.relatorio()
    assert (r["votes"], r["useful"], r["not_useful"]) == (4, 2, 2)
    assert r["worst_sources"] == [{"path": "Sessions/x.md", "useful": 0, "not_useful": 2}]
    assert r["queries_without_a_useful_result"] == ["quem e o contato"]

    dados = feedback_busca.para_avaliacao()
    assert dados == [{"pergunta": "deploy porta", "esperado": {"Fixes/deploy.md": 3}}]
    destino = tmp_path / "q.json"
    assert feedback_busca.cmd_feedback(SimpleNamespace(acao="export", out=str(destino), days=0, force=False)) == 0
    assert avaliacao.carregar(destino)[0].graus == {"Fixes/deploy.md": 3}, "o export e lido pela avaliacao"
    assert feedback_busca.cmd_feedback(SimpleNamespace(acao="export", out=str(destino), days=0, force=False)) == 1


def test_consulta_com_segredo_e_coberta():
    r = feedback_busca.votar("chave sk-ant-api03-" + "Q" * 90, "a.md", 1)
    assert "QQQQQQQQQQ" not in json.dumps(r)


def test_ferramentas():
    r = json.loads(server.search_feedback(query="q", path="a.md", vote=1))
    assert r["status"] == "ok"
    r = json.loads(server.search_feedback(query="q", path="a.md", vote=5))
    assert "vote must be" in json.dumps(r)
    assert json.loads(server.feedback_report())["votes"] == 1
