"""O que mudou na base de codigo desde o grafo anterior.

## Por que isto existe

`graph.analyze.graph_diff` estava implementada, testada e **sem nenhum
chamador**. O `capabilities()` a listava em `known_unwired` com a frase "never
surfaced; would answer 'what changed in this codebase since the last graph'".

Das cinco capacidades sem fio que esse relatorio lista, quatro foram medidas em
25 e 26/09/2026 e **recusadas**, porque nao tinham sobre o que agir nesta casa:
`detect_incremental` (extracao fria custa o mesmo que quente),
`remap_communities_to_previous` e `community_member_sigs` (nada na saida usa id
de comunidade) e `assert_valid` (quebraria todo build). Esta e a unica que
sobrou sendo lacuna de verdade, e o que faltava era so ter contra o que
comparar.

## O custo, medido antes de ligar

| | |
|---|---|
| carregar o grafo anterior (6,9 MB) | 0,10s |
| carregar o novo | 0,10s |
| diff | 0,04s |
| **total** | **0,23s** |

Contra um build que hoje leva dezenas de segundos, e desprezivel. Medir antes
importava porque o arquivamento incremental acabou de derrubar o custo do
build, e seria tolo devolver parte dele.

## O resumo e limitado de proposito

Este projeto ja pagou por devolver lista crua: `vault_paths` no registro de
grafos chegou a 1441 entradas e os seis grafos juntos somaram 181.666
caracteres, passando do teto de resultado do MCP, e a ferramenta devolvia nada
de util. A licao ficou escrita no `list_graphs`.

Um diff de base grande tem a mesma forma: renomear um pacote muda milhares de
nos. Entao sai **contagem sempre, e amostra limitada**, com o total ao lado
para quem le saber que a amostra e amostra.

## Criterio de lego

Recebe dois caminhos e devolve um dicionario. Nao sabe o que e vault, daemon,
MCP nem registro de grafos. Da para apagar este modulo e o build volta ao que
era, perdendo so a resposta.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("diferenca")

#: Quantos nomes acompanham cada contagem. Dez cabe numa tela e basta para
#: reconhecer o que mudou; o total vai junto para a amostra nao se passar por
#: lista completa.
AMOSTRA = 10


def _amostrar(itens: list[dict], chave: str = "label") -> list[str]:
    nomes = sorted(str(i.get(chave) or i.get("id") or "?") for i in itens)
    return nomes[:AMOSTRA]


def comparar(anterior: "str | Path", atual: "str | Path") -> dict | None:
    """O que mudou entre dois `graph.json`, ou None quando nao da para saber.

    Devolve None, e nao um dicionario vazio, quando o grafo anterior nao existe:
    "nao havia com o que comparar" e "comparei e nada mudou" sao respostas
    diferentes, e quem le o resultado do build precisa distinguir as duas. O
    primeiro build de um grafo cai sempre no primeiro caso.

    Falha calada por escolha: um diff que nao sai nao pode derrubar um build que
    ja terminou. O log nomeia o par para quem for investigar.
    """
    from .graph.affected import load_graph
    from .graph.analyze import graph_diff

    caminho_anterior, caminho_atual = Path(anterior), Path(atual)
    if not caminho_anterior.is_file() or not caminho_atual.is_file():
        return None

    try:
        antigo = load_graph(caminho_anterior)
        novo = load_graph(caminho_atual)
        bruto = graph_diff(antigo, novo)
    except Exception as e:
        logger.warning("diff de grafo falhou entre %s e %s (%s)",
                       caminho_anterior, caminho_atual, e)
        return None

    nos_novos = bruto.get("new_nodes") or []
    nos_idos = bruto.get("removed_nodes") or []
    arestas_novas = bruto.get("new_edges") or []
    arestas_idas = bruto.get("removed_edges") or []

    return {
        "nos_novos": len(nos_novos),
        "nos_removidos": len(nos_idos),
        "arestas_novas": len(arestas_novas),
        "arestas_removidas": len(arestas_idas),
        "amostra_nos_novos": _amostrar(nos_novos),
        "amostra_nos_removidos": _amostrar(nos_idos),
        "resumo": bruto.get("summary", ""),
        "sem_mudanca": not (nos_novos or nos_idos or arestas_novas or arestas_idas),
    }
