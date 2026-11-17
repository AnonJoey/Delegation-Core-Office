"""Ciclo de vida do Read no proxy: o `ReadLifecycleManager` do Headroom, com o armazem do delegation-core.

Um Read cujo arquivo foi editado depois (Edit ou Write) mostra ao modelo um conteudo que ja nao e o do
disco: ele so atrapalha, e a releitura e o que vale. Esse resultado vira um marcador curto com a chave
do original, que o `recall_output` devolve:

    [Read content stale: src/a.py was modified after this read, re-read the file for current content.
     Retrieve original: hash=<24 hex>]

Um Read refeito inteiro depois (`superseded`) e redundante e pode virar o mesmo tipo de marcador, mas
fica desligado a parte (`proxy_read_superseded`). Leitura recente (fresca) nunca e tocada, nem a menor
que 512 bytes.

Ao contrario do dedup entre turnos, isto TROCA bytes de turnos anteriores: no turno em que o Edit
aparece, o prefixo que o provedor guardou em cache muda dali em diante, uma vez (depois fica estavel).
Por isso e opcional (`proxy_read_lifecycle`).

O `read_lifecycle.py` e copia byte a byte do Headroom; aqui so entram o armazem e a leitura da flag.
Cobre `tool_result` do Anthropic com conteudo em texto e `role: tool` do OpenAI Chat.
"""

from __future__ import annotations

import logging

from ..compressao.ccr import Guarda
from ..compressao.headroom_py.config import ReadLifecycleConfig
from ..compressao.headroom_py.transforms.read_lifecycle import ReadLifecycleManager, ReadLifecycleResult

logger = logging.getLogger("proxy")


class _Armazem:
    """O `compression_store` que o manager espera, sobre a guarda CCR do delegation-core."""

    def __init__(self, guarda: Guarda | None = None):
        self.guarda = guarda or Guarda()

    def store(self, original: str, compressed: str, tool_name: str, tool_call_id: str,
              compression_strategy: str, explicit_hash: str) -> str:
        self.guarda.put(explicit_hash, original)
        return explicit_hash


def aplicar(mensagens: list, *, superseded: bool = False, guarda: Guarda | None = None) -> ReadLifecycleResult:
    """O manager sobre as mensagens; qualquer erro devolve as mensagens como vieram."""
    try:
        gerente = ReadLifecycleManager(ReadLifecycleConfig(enabled=True, compress_superseded=superseded),
                                       _Armazem(guarda))
        return gerente.apply(mensagens)
    except Exception as e:  # noqa: BLE001 - acessorio: o que falha vai como veio
        logger.warning("proxy: read lifecycle skipped (%s)", type(e).__name__)
        return ReadLifecycleResult(messages=mensagens)
