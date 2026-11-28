"""Anotacoes MCP de cada ferramenta, derivadas da classificacao que ja existe.

Trazido do REA (`src/contracts/toolEffects.ts`): cada ferramenta declara os
efeitos, e as dicas do protocolo (`readOnlyHint`, `destructiveHint`,
`idempotentHint`, `openWorldHint`) saem deles, nunca escritas a mao uma a uma.

Aqui a fonte e a que o servidor ja usa para autorizar: `escopos.LEITURA` e
`escopos.ESCRITA`, mais `governanca.DESTRUTIVAS`. Uma classificacao so, que
autoriza e anuncia; nao ha como as duas divergirem.

As dicas sao dicas: o cliente decide o que fazer com elas, e quem garante e o
escopo do token e a politica. Ferramenta sem classificacao sai como escrita.
"""

from __future__ import annotations

#: Ferramentas que falam com o mundo de fora da maquina. Um comando de shell alcanca o que quiser.
MUNDO_ABERTO = frozenset({"search_web", "dag_run"})


def anotacoes_de(nome: str) -> dict:
    from . import escopos
    from .governanca import DESTRUTIVAS
    leitura = nome in escopos.LEITURA
    return {
        "readOnlyHint": leitura,
        "destructiveHint": nome in DESTRUTIVAS,
        "idempotentHint": leitura,
        "openWorldHint": nome in MUNDO_ABERTO,
    }


async def aplicar(mcp) -> int:
    """Poe as anotacoes em toda ferramenta registrada. Devolve quantas."""
    from mcp.types import ToolAnnotations
    n = 0
    for t in await mcp.list_tools():
        atual = t.annotations.model_dump(exclude_none=True) if t.annotations else {}
        t.annotations = ToolAnnotations(**{**anotacoes_de(t.name), **{k: v for k, v in atual.items() if k == "title"}})
        n += 1
    return n
