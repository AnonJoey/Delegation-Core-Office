"""Liga a autoridade (`ranqueamento.autoridade`) a busca do vault: nota mantida sobe, nota velha desce.

A autoridade e um fator limitado (0,55 a 1,50) que desempata a favor do que e mantido: uma decisao,
um procedimento ou uma nota marcada `canonical` passam uma sessao antiga, e uma nota `superseded` ou
`historical` desce sem sair da busca. Os fatores e os limites sao os do ai-memory (MIT, Fabio Akita).

## Sobre o posto, e nao a similaridade

O fator multiplica a nota de **posto** (RRF, `1 / (60 + posicao)`), como no original, e nao a
similaridade do cosseno. Multiplicar a similaridade deixaria 0,60 de uma decisao passar 0,95 de uma
sessao, e o resultado dependeria da escala de cada reordenador. Pelo posto a conta e a do original:
as notas das posicoes 1 e 10 diferem por 1,15 vezes, as das posicoes 1 e 40 por 1,64.

Isso e forte, de proposito: uma decisao semantica (1,25) alcanca uma sessao (0,77, razao 1,62) que
esteja em primeiro lugar ate cerca da posicao 38, e por isso o original le quatro vezes mais
candidatos do que devolve (`candidatos`). Quem acha demais ajusta `autoridade_forca` na config, que
escala o desvio de cada fator em relacao a 1,0 (1,0 e o original, 0,5 e metade do efeito, 0 desliga).

Um vault de notas nao tem o "tipo" e a "camada" do original, entao eles vem da pasta (`TIPO_POR_PASTA`):
`Decisions` sao decisoes semanticas; `Sessions` sao sessoes episodicas. Etiquetas (`tags:`) e
`pinned: true` vem do frontmatter. Acerto que nao e nota do vault (artigo gerado, arquivo externo)
fica com fator 1,0.

Quando a pergunta e sobre uma sessao passada ("o que fizemos na ultima sessao"), a penalidade da
sessao some e ainda ganha um bonus (`eh_pergunta_de_sessao`), senao a busca esconderia justamente
o que foi pedido.

Desligado por padrao: `autoridade_enabled=false` na config.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .cabeca_da_nota import frontmatter_de, ler_cabeca
from .ranqueamento.autoridade import (
    autoridade_da_nota,
    eh_pergunta_de_sessao,
    limite_de_candidatos,
    multiplicar_posto,
)

logger = logging.getLogger(__name__)

#: pasta do vault -> (tipo, camada) no vocabulario do ai-memory
TIPO_POR_PASTA = {
    "Decisions": ("decision", "semantic"),
    "Procedures": ("procedure", "procedural"),
    "Tools": ("procedure", "procedural"),
    "Fixes": ("gotcha", "semantic"),
    "Reference": ("concept", "semantic"),
    "Infrastructure": ("concept", "semantic"),
    "Projects": ("concept", "semantic"),
    "Sessions": ("session", "episodic"),
    "Scratch": ("session", "working"),
}
BONUS_DE_SESSAO = 0.25
#: A constante do RRF: o mesmo 60 de `ranqueamento.fusao.rrf`.
RRF_K = 60


def ligado(cfg) -> bool:
    return bool(getattr(cfg, "autoridade_enabled", False))


def candidatos(cfg, limite: int) -> int:
    """Quantos acertos buscar para poder reordenar e ainda devolver `limite`."""
    return limite_de_candidatos(limite) if ligado(cfg) else limite


def fator_da_nota(cfg, rel: str, de_sessao: bool = False) -> float:
    """O fator de autoridade de uma nota do vault; 1,0 para o que nao e nota (ou nao tem tipo conhecido)."""
    pasta = rel.split("/", 1)[0]
    if pasta not in TIPO_POR_PASTA:
        return 1.0
    tipo, camada = TIPO_POR_PASTA[pasta]
    cabeca = ler_cabeca(Path(cfg.vault) / rel)
    fm = frontmatter_de(cabeca) if cabeca else {}
    a = autoridade_da_nota(rel, tipo, camada, fm.get("pinned") is True, fm)
    fator = a.fator_para(de_sessao, BONUS_DE_SESSAO)
    forca = getattr(cfg, "autoridade_forca", 1.0)
    return 1.0 + max(0.0, float(forca)) * (fator - 1.0) if forca != 1.0 else fator


def reordenar(cfg, consulta: str, acertos: list[dict], limite: int) -> list[dict]:
    """Reordena os acertos pelo posto vezes a autoridade e devolve os `limite` primeiros.

    A similaridade de cada acerto nao muda (a confianca da busca continua sendo a real); cada um ganha
    `authority`, o fator aplicado. Os acertos chegam em ordem de relevancia. Nunca levanta: se algo
    falhar, a ordem original vale.
    """
    if not ligado(cfg) or not acertos:
        return acertos[:limite]
    try:
        sessao = eh_pergunta_de_sessao(consulta)
        pontos = []
        for i, h in enumerate(acertos):
            f = fator_da_nota(cfg, h.get("path", ""), sessao) if h.get("kind", "note") == "note" else 1.0
            h["authority"] = round(f, 3)
            # o posto do porte e "menor e melhor": a nota RRF entra negada
            pontos.append((multiplicar_posto(-1.0 / (RRF_K + i + 1), f), i))
        pontos.sort()
        return [acertos[i] for _, i in pontos][:limite]
    except Exception as e:  # noqa: BLE001 - a autoridade e um desempate, nao pode derrubar a busca
        logger.warning("autoridade nao reordenou a busca: %s", e)
        return acertos[:limite]
