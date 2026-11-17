"""Avaliacao de busca: acerto, MRR, nDCG graduado, latencia, metas e o arquivo."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from delegation_core import avaliacao


def test_carregar_lista_e_graus(tmp_path):
    arq = tmp_path / "c.json"
    arq.write_text(json.dumps([
        {"pergunta": "a", "esperado": "x.md"},
        {"pergunta": "b", "esperado": {"y.md": 3, "z.md": 1, "w.md": 0}},
    ]))
    c = avaliacao.carregar(arq)
    assert c[0].graus == {"x.md": 1} and c[1].esperado == ["y.md", "z.md"]
    arq.write_text(json.dumps([{"pergunta": "a", "esperado": {"x": 4}}]))
    with pytest.raises(ValueError, match="0 a 3"):
        avaliacao.carregar(arq)
    arq.write_text(json.dumps([{"pergunta": "a", "esperado": {"x": 0}}]))
    with pytest.raises(ValueError, match="sem"):
        avaliacao.carregar(arq)


def test_ndcg():
    g = {"a": 3, "b": 1}
    assert avaliacao.ndcg(["a", "b"], g, 5) == pytest.approx(1.0)
    invertido = avaliacao.ndcg(["b", "a"], g, 5)
    assert 0 < invertido < 1
    assert avaliacao.ndcg(["x", "y"], g, 5) == 0.0
    assert avaliacao.ndcg(["a1", "a2"], {"a": 1}, 5) == pytest.approx(1.0), "um trecho conta uma vez"


def test_avaliar_mrr_ndcg_latencia_e_meta():
    respostas = {"q1": ["Ref/a.md", "x"], "q2": ["x", "Ref/b.md"], "q3": ["x"]}
    consultas = [avaliacao.Consulta("q1", {"a.md": 1}), avaliacao.Consulta("q2", {"b.md": 1}),
                 avaliacao.Consulta("q3", {"c.md": 1})]
    t = iter(range(0, 1000, 1))
    r = avaliacao.avaliar(consultas, lambda q, e, k: respostas[q], ["notes"], k=5,
                          relogio=lambda: next(t) / 100)[0]
    assert (r.acertos, r.total, r.mrr) == (2, 3, 0.5)
    assert r.erros == [{"pergunta": "q3", "voltou": ["x"]}]
    assert r.percentil(0.5) == 10.0 and r.resumo()["latencia_ms"]["p95"] == 10.0
    assert len(r.abaixo_da_meta()) == 2 and r.abaixo_da_meta(0.4, 0.4) == []


def test_cli_portao(monkeypatch, tmp_path, capsys):
    arq = tmp_path / "c.json"
    arq.write_text(json.dumps([{"pergunta": "q", "esperado": ["a.md"]}]))
    monkeypatch.setattr(avaliacao, "buscador_do_daemon", lambda cfg: lambda q, e, k: ["x", "a.md"])
    ns = dict(arquivo=str(arq), scope="notes", k=5, json=False, min_mrr=0.95, min_ndcg=0.9)
    assert avaliacao.cmd_eval_search(SimpleNamespace(gate=False, **ns)) == 0
    assert avaliacao.cmd_eval_search(SimpleNamespace(gate=True, **ns)) == 1
    assert "abaixo da meta" in capsys.readouterr().out


# ── casos do PR 23 da producao (eval-search original) ──



def _arquivo(tmp_path, dados):
    p = tmp_path / "consultas.json"
    p.write_text(json.dumps(dados), encoding="utf-8")
    return p


def test_acerto_e_trecho_do_caminho_em_qualquer_posicao_ate_k():
    assert avaliacao.posicao_do_acerto(["a/x.md", "b/alvo.md"], ["alvo"]) == 2
    assert avaliacao.posicao_do_acerto(["a/x.md"], ["alvo"]) == 0


def test_qualquer_um_dos_esperados_vale():
    assert avaliacao.posicao_do_acerto(["c/outro.md"], ["alvo", "outro"]) == 1


def test_consulta_sem_esperado_e_recusada(tmp_path):
    """Uma consulta que nao diz o que conta como acerto so poderia ser erro."""
    with pytest.raises(ValueError):
        avaliacao.carregar(_arquivo(tmp_path, [{"pergunta": "x"}]))


def test_esperado_como_texto_vira_lista(tmp_path):
    cs = avaliacao.carregar(_arquivo(tmp_path, [{"pergunta": "x", "esperado": "alvo"}]))
    assert cs[0].esperado == ["alvo"]


def test_avaliar_conta_por_escopo_e_corta_em_k():
    cs = [avaliacao.Consulta("p1", ["alvo1"]), avaliacao.Consulta("p2", ["alvo2"])]
    respostas = {
        ("p1", "a"): ["alvo1.md"],
        ("p2", "a"): ["x", "y", "alvo2.md"],      # na posicao 3: fora de k=2
        ("p1", "b"): ["x", "alvo1.md"],
        ("p2", "b"): ["alvo2.md"],
    }
    r = avaliacao.avaliar(cs, lambda q, e, k: respostas[(q, e)], ["a", "b"], k=2)
    a, b = (x.resumo() for x in r)
    assert (a["acertos"], a["mrr"]) == (1, 0.5)
    assert [e["pergunta"] for e in a["erros"]] == ["p2"]
    assert (b["acertos"], b["mrr"]) == (2, 0.75)
