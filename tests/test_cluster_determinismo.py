"""A particao nao pode depender da ORIENTACAO com que as arestas chegam.

## O defeito, medido em 25/09/2026

Num grafo nao dirigido, `G.edges()` devolve cada aresta numa orientacao que
depende da iteracao interna de adjacencia, e ela **varia entre processos**.
Medido no subgrafo da maior comunidade deste repo, das 1675 arestas vinham
invertidas 938, 793 e 987 em tres execucoes da mesma fonte, sem nada ter
mudado no codigo.

`_partition` ordenava as arestas por `(str(row[0]), str(row[1]))`, ou seja pela
orientacao RECEBIDA. A sequencia de insercao em `stable` mudava a cada
processo, e o Louvain, que e sensivel a ordem no desempate, devolvia particoes
diferentes: `cluster()` dava 312, 313 ou 314 comunidades para o mesmo grafo.

Nada disso aparecia como erro. O sintoma era um `graph_build` reescrever
artigos intocados e "comunidade 137" significar coisas diferentes em dois
relatorios do mesmo commit.

## O que ficou provado estavel, para nao confundir os culpados

Extracao e construcao do grafo **sempre** foram deterministas: 6321 nos e
11453 arestas, mesmo hash em 5 de 5 execucoes. A instabilidade era so do
agrupamento.

## O QUE ESTES TESTES SAO, E O QUE ELES NAO SAO

Eles guardam uma **propriedade** que o modulo passou a garantir: a particao nao
pode depender da orientacao com que as arestas chegam. Isso e desejavel por si
so e e o que a correcao implementa.

**Eles NAO reproduzem o defeito, e dizer que reproduzem seria mentira.**
Conferido por mutacao: com a normalizacao removida das duas pontas, chave de
ordenacao e insercao, estes quatro testes continuam verdes. O Louvain so e
sensivel a ordem de insercao quando ha empate farto, e as formas sinteticas que
tentei nao produzem esse empate: 18 grafos densos e esparsos, inversao total e
inversao parcial a cada 2, 3, 5 e 7 arestas, nenhum reproduziu. Quem reproduzia
era o subgrafo real de 679 nos e 1675 arestas com coesao abaixo de 0,05, e
guardar 1675 arestas como fixture era caro demais para o que provaria.

**A evidencia do defeito e a medicao, nao a suite:**

| | Antes | Depois |
|---|---|---|
| divisao por coesao, execucoes iguais | 0 de 5 (299, 300, 301, 301, 301) | **9 de 9** |
| `cluster()` completo | 312, 313, 314 | **9 de 9 iguais** |
| hash da sequencia de insercao em `_partition` | 3 hashes em 3 execucoes | **1 hash em 3** |

Quem mexer aqui e quiser conferir de verdade roda `cluster()` em tres
processos separados sobre o mesmo repo e compara. A suite sozinha nao avisa.
"""

from __future__ import annotations

import networkx as nx
import pytest

from delegation_core.graph.cluster import _partition, cluster


def _grafo_com_empates() -> nx.Graph:
    """Dois blocos densos ligados por poucas pontes, construido sem aleatoriedade.

    Empate farto de proposito: e no desempate que a ordem de insercao decide, e
    um grafo sem empate passaria mesmo com o defeito no lugar.
    """
    G = nx.Graph()
    for i in range(120):
        for j in range(i + 1, 120):
            if (i * 7 + j * 13) % 11 == 0:
                G.add_edge(f"no_{i:03d}", f"no_{j:03d}", weight=1.0)
    for i in range(120, 240):
        for j in range(i + 1, 240):
            if (i * 5 + j * 17) % 11 == 0:
                G.add_edge(f"no_{i:03d}", f"no_{j:03d}", weight=1.0)
    for k in range(0, 120, 17):
        G.add_edge(f"no_{k:03d}", f"no_{k+120:03d}", weight=1.0)
    return G


def _invertido(G: nx.Graph) -> nx.Graph:
    """O MESMO grafo, com cada aresta inserida na orientacao contraria.

    E exatamente o que a iteracao de adjacencia faz sozinha entre processos, e
    para um grafo nao dirigido as duas formas descrevem o mesmo grafo.
    """
    H = nx.Graph()
    H.add_nodes_from(G.nodes())
    for a, b, d in G.edges(data=True):
        H.add_edge(b, a, **d)
    return H


def _grupos(particao: dict) -> set[frozenset]:
    saida: dict[int, set] = {}
    for no, cid in particao.items():
        saida.setdefault(cid, set()).add(no)
    return {frozenset(v) for v in saida.values()}


def test_o_grafo_invertido_e_o_mesmo_grafo():
    """Guarda do proprio teste: se os dois grafos nao forem iguais, o teste
    abaixo estaria comparando coisas diferentes e nao provaria nada."""
    G = _grafo_com_empates()
    H = _invertido(G)
    assert set(G.nodes()) == set(H.nodes())
    assert ({frozenset((a, b)) for a, b in G.edges()}
            == {frozenset((a, b)) for a, b in H.edges()})


def test_a_particao_nao_muda_com_a_orientacao_das_arestas():
    """A propriedade: mesma particao, qualquer que seja a orientacao recebida.

    Nao confunda com o defeito: este teste sobrevive a mutacao (veja o
    docstring do modulo). Ele fixa o contrato para quem mexer no `_partition`
    depois, nao reproduz a instabilidade entre processos.
    """
    G = _grafo_com_empates()
    assert _grupos(_partition(G)) == _grupos(_partition(_invertido(G))), (
        "a particao dependeu da orientacao com que as arestas foram inseridas")


def test_cluster_completo_nao_muda_com_a_orientacao():
    """O mesmo, ponta a ponta: e `cluster()` que o `graph_build` chama."""
    G = _grafo_com_empates()
    a = {frozenset(nos) for nos in cluster(G).values()}
    b = {frozenset(nos) for nos in cluster(_invertido(G)).values()}
    assert a == b


@pytest.mark.parametrize("repeticoes", [3])
def test_a_particao_e_estavel_entre_chamadas(repeticoes):
    """Guarda de base: instabilidade DENTRO do processo seria outro defeito,
    e distinguir os dois foi metade do trabalho de achar este."""
    G = _grafo_com_empates()
    primeiro = _grupos(_partition(G))
    for _ in range(repeticoes):
        assert _grupos(_partition(G)) == primeiro
