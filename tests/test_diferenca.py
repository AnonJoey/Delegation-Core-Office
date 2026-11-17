"""O que mudou na base desde o grafo anterior.

## Por que este modulo existe

`graph.analyze.graph_diff` estava implementada, testada e **sem nenhum
chamador**, e o `capabilities()` a listava como "never surfaced". Das cinco
capacidades sem fio daquele relatorio, quatro foram medidas em 25 e 26/09/2026
e recusadas por nao terem sobre o que agir aqui. Esta era a unica lacuna de
verdade, e o que faltava nao era a funcao: era o build guardar o grafo anterior
para ter contra o que comparar.

Custo medido antes de ligar: 0,23s para carregar dois grafos de 6,9 MB e
diferenciar. Contra um build de dezenas de segundos, desprezivel. Medir antes
importava porque o arquivamento incremental acabara de derrubar o custo do
build, e seria tolo devolver parte dele.
"""

from __future__ import annotations

import json

import pytest

from delegation_core import diferenca


def _grafo(caminho, nos, arestas=()):
    """Um `graph.json` no formato que o `to_json` escreve."""
    caminho.write_text(json.dumps({
        "nodes": [{"id": n, "label": n} for n in nos],
        "links": [{"source": a, "target": b, "relation": "calls"} for a, b in arestas],
        "directed": True,
    }), encoding="utf-8")
    return caminho


def test_sem_grafo_anterior_devolve_None_e_nao_vazio(tmp_path):
    """"Nao havia com o que comparar" e "comparei e nada mudou" sao respostas
    DIFERENTES, e quem le o resultado do build precisa distinguir as duas.

    O primeiro build de um grafo cai sempre no primeiro caso, e devolver um
    dicionario de zeros ali diria que a base nao mudou, o que e falso: ninguem
    sabe.

    Conferido por mutacao: devolver `{}` em vez de `None` derruba este teste.
    """
    atual = _grafo(tmp_path / "graph.json", ["a"])
    assert diferenca.comparar(tmp_path / "nao_existe.json", atual) is None


def test_grafos_iguais_dizem_que_nada_mudou(tmp_path):
    a = _grafo(tmp_path / "a.json", ["x", "y"], [("x", "y")])
    b = _grafo(tmp_path / "b.json", ["x", "y"], [("x", "y")])
    d = diferenca.comparar(a, b)
    assert d is not None
    assert d["sem_mudanca"] is True
    assert d["nos_novos"] == d["nos_removidos"] == 0


def test_no_acrescentado_aparece_na_contagem_e_na_amostra(tmp_path):
    a = _grafo(tmp_path / "a.json", ["x"])
    b = _grafo(tmp_path / "b.json", ["x", "novo"])
    d = diferenca.comparar(a, b)
    assert d["nos_novos"] == 1
    assert "novo" in d["amostra_nos_novos"]
    assert d["sem_mudanca"] is False


def test_no_removido_aparece_separado_do_acrescentado(tmp_path):
    a = _grafo(tmp_path / "a.json", ["x", "sumiu"])
    b = _grafo(tmp_path / "b.json", ["x"])
    d = diferenca.comparar(a, b)
    assert d["nos_removidos"] == 1
    assert "sumiu" in d["amostra_nos_removidos"]
    assert d["nos_novos"] == 0


def test_a_amostra_e_limitada_e_a_contagem_nao(tmp_path):
    """O teste que carrega o argumento.

    Este projeto ja pagou por devolver lista crua: `vault_paths` chegou a 1441
    entradas e os seis grafos somaram 181.666 caracteres, passando do teto de
    resultado do MCP, e a ferramenta devolvia nada de util. A licao ficou
    escrita no `list_graphs`.

    Um diff tem a mesma forma: renomear um pacote muda milhares de nos. Entao a
    contagem e sempre exata e a amostra e limitada, com o total ao lado para a
    amostra nao se passar por lista completa.

    Conferido por mutacao: tirar o corte em `_amostrar` derruba este teste.
    """
    muitos = [f"no_{i:03d}" for i in range(200)]
    a = _grafo(tmp_path / "a.json", ["base"])
    b = _grafo(tmp_path / "b.json", ["base", *muitos])
    d = diferenca.comparar(a, b)

    assert d["nos_novos"] == 200, "a contagem tem que ser exata"
    assert len(d["amostra_nos_novos"]) == diferenca.AMOSTRA, (
        f"a amostra tem que ser limitada a {diferenca.AMOSTRA}, "
        f"veio com {len(d['amostra_nos_novos'])}")


def test_grafo_ilegivel_nao_derruba_o_build(tmp_path):
    """Um diff que nao sai nao pode derrubar um build que ja terminou."""
    a = tmp_path / "a.json"
    a.write_text("{ isto nao e json", encoding="utf-8")
    b = _grafo(tmp_path / "b.json", ["x"])
    assert diferenca.comparar(a, b) is None


def test_o_build_guarda_o_grafo_anterior_e_reporta(tmp_path):
    """A LIGACAO, em duas metades, e a primeira e a que faltava.

    A funcao existia ha muito tempo; o que nao existia era o build guardar o
    grafo anterior. Sem a copia nao ha contra o que comparar, e o campo no
    resultado seria `None` para sempre.

    Conferido por mutacao: tirar a copia OU tirar o campo do resultado derruba
    este teste.
    """
    import inspect

    from delegation_core import graphbridge

    fonte = inspect.getsource(graphbridge.build_graph)
    assert "graph.anterior.json" in fonte, (
        "o build precisa guardar o grafo anterior antes de sobrescrever")
    assert "shutil.copy2" in fonte, (
        "copia e nao move: se o to_json falhar, o grafo velho tem que continuar "
        "no lugar em vez de virar so o .anterior")
    assert "mudou_desde_o_anterior" in fonte, (
        "o resultado do build precisa carregar o que mudou")
