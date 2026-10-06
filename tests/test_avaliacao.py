"""O avaliador de busca: o que conta como acerto, e o que ele recusa."""

import json

import pytest

from delegation_core import avaliacao


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
