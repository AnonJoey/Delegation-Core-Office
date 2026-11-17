"""Recuperacao hibrida: lexico (BM25) + denso, fundidos por RRF, com reordenacao opcional.

Pacote independente. O nucleo do delegation-core nao importa nada daqui a nao
ser que a busca hibrida esteja ligada, e este pacote nao importa nada do
nucleo: recebe listas e textos, devolve listas.

- `lexico.IndiceLexico`: FTS5 com BM25, incremental por mtime
- `fusao.rrf`: Reciprocal Rank Fusion, funcao pura
- `rerank.CrossEncoderReordenador`: cross-encoder opcional sobre os primeiros
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .fusao import rrf
from .lexico import IndiceLexico
from .rerank import CrossEncoderReordenador, Reordenador, reordenar

__all__ = ["IndiceLexico", "rrf", "CrossEncoderReordenador", "Reordenador",
           "reordenar", "combinar"]


def combinar(
    consulta: str,
    densos: Sequence[str],
    lexicos: Sequence[str],
    limite: int = 10,
    pesos: tuple[float, float] = (1.0, 1.0),
    reordenador: Reordenador | None = None,
    texto_de: Callable[[str], str] | None = None,
    profundidade_rerank: int = 20,
    pontos_lexicos: Sequence[float] | None = None,
    razao_dominante: float | None = None,
) -> list[str]:
    """A lista final de ids.

    Funde denso e lexico por RRF; se houver reordenador, ele reordena os
    `profundidade_rerank` primeiros da fusao lendo o texto de cada um, e o
    resto da fusao segue atras na ordem que tinha.

    `razao_dominante`: se o primeiro lexico tiver BM25 pelo menos essa razao
    acima do segundo (`pontos_lexicos`, na ordem de `lexicos`), ele vai para o
    topo depois da reordenacao. O reordenador le sentido e desmonta acerto
    exato: frase copiada de uma nota tinha R@1 0,967 so no lexico e caiu para
    0,483 depois de reordenada. Ver ENRIQUECIMENTO.md para a medicao do limiar.
    """
    fundidos = [d for d, _ in rrf([list(densos), list(lexicos)], pesos=list(pesos))]
    if reordenador is None or texto_de is None:
        return fundidos[:limite]
    topo = fundidos[:profundidade_rerank]
    reord = [d for d, _ in reordenar(consulta, [(d, texto_de(d)) for d in topo], reordenador)]
    saida = reord + fundidos[profundidade_rerank:]
    if razao_dominante and pontos_lexicos and lexicos:
        p = list(pontos_lexicos)
        dominante = len(p) == 1 or (len(p) > 1 and p[1] > 0 and p[0] / p[1] >= razao_dominante)
        if dominante:
            fixo = lexicos[0]
            saida = [fixo] + [d for d in saida if d != fixo]
    return saida[:limite]
