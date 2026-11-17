"""Fusao de listas ranqueadas por Reciprocal Rank Fusion.

RRF soma, para cada documento, `peso / (k + posicao)` em cada lista em que ele
aparece. Nao olha a pontuacao de nenhuma lista, so a posicao, e e isso que
permite juntar similaridade de cosseno (0 a 1) com BM25 (sem teto) sem
calibrar escala nenhuma. `k = 60` e o valor do artigo original (Cormack,
Clarke e Buettcher, 2009) e o padrao de quase todo motor que faz busca hibrida.

Funcao pura: listas entram, lista sai.
"""

from __future__ import annotations

from collections.abc import Sequence


def rrf(
    listas: Sequence[Sequence[str]],
    k: int = 60,
    pesos: Sequence[float] | None = None,
    limite: int | None = None,
) -> list[tuple[str, float]]:
    """Funde listas de ids (a melhor primeiro) em uma, com a pontuacao RRF.

    Id repetido dentro da mesma lista conta so na primeira posicao. Empate de
    pontuacao mantem a ordem em que o id apareceu pela primeira vez, lendo as
    listas em ordem: e o `sorted` estavel sobre um dict que preserva insercao.
    Uma chave de desempate pela melhor posicao chegou a existir e saiu, porque
    a mutacao mostrou que ela nao alcanca caso nenhum com pesos inteiros.
    """
    if pesos is None:
        pesos = [1.0] * len(listas)
    if len(pesos) != len(listas):
        raise ValueError("um peso por lista")

    pontos: dict[str, float] = {}
    for lista, peso in zip(listas, pesos):
        vistos: set[str] = set()
        for pos, doc in enumerate(lista, start=1):
            if doc in vistos:
                continue
            vistos.add(doc)
            pontos[doc] = pontos.get(doc, 0.0) + peso / (k + pos)

    saida = sorted(pontos.items(), key=lambda kv: -kv[1])
    return saida[:limite] if limite else saida
