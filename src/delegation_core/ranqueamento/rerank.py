"""Reordenar candidatos lendo consulta e texto juntos (cross-encoder).

O embedding denso codifica consulta e nota separadas e compara vetores; o
cross-encoder le as duas na mesma passada e decide o quanto uma responde a
outra. E mais caro por par e muito mais preciso, entao so vale sobre poucos
candidatos ja filtrados, que e onde o grafana o poe
(`pkg/storage/unified/search/rerank/`).

O modelo padrao e o `BAAI/bge-reranker-v2-m3`: multilingue, e da mesma familia
do bge-m3 que ja embute este vault.

## Contrato

Qualquer objeto com `pontuar(consulta, textos) -> list[float]` serve. O resto
do pacote so conhece esse metodo, entao trocar de modelo, ou reordenar com o
modelo local via llama.cpp, nao toca em quem chama.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Protocol

logger = logging.getLogger("ranqueamento.rerank")

MODELO_PADRAO = "BAAI/bge-reranker-v2-m3"


class Reordenador(Protocol):
    def pontuar(self, consulta: str, textos: Sequence[str]) -> list[float]: ...


class CrossEncoderReordenador:
    """sentence-transformers CrossEncoder, carregado na primeira chamada.

    `dispositivo` segue a mesma regra do `embed_device`: "cpu", "cuda" ou
    "auto". Na maquina de producao o llama.cpp ocupa a placa inteira por
    decisao, entao o padrao e "cpu".
    """

    def __init__(self, modelo: str = MODELO_PADRAO, dispositivo: str = "cpu",
                 max_caracteres: int = 2000, lote: int = 16, meia_precisao: bool = True):
        self.modelo = modelo
        self.dispositivo = dispositivo
        #: Em GPU, fp16 corta a memoria pela metade (2,2 GB para ~1,1 GB). Medido:
        #: duas copias fp32 ao lado do llama (10,7 GB) estouraram a placa de 16 GB.
        #: Em CPU fp16 e mais lento, entao so vale na placa.
        self.meia_precisao = meia_precisao
        self.max_caracteres = max_caracteres
        self.lote = lote
        self._ce = None
        self._trava = threading.Lock()

    def _carregar(self):
        with self._trava:
            if self._ce is None:
                from sentence_transformers import CrossEncoder

                disp = None if self.dispositivo == "auto" else self.dispositivo
                self._ce = CrossEncoder(self.modelo, device=disp, max_length=512)
                if self.meia_precisao and str(self._ce.device).startswith("cuda"):
                    self._ce.model.half()
                logger.info("reordenador %s carregado em %s", self.modelo, self._ce.device)
        return self._ce

    def pontuar(self, consulta: str, textos: Sequence[str]) -> list[float]:
        if not textos:
            return []
        ce = self._carregar()
        pares = [(consulta, (t or "")[: self.max_caracteres]) for t in textos]
        return [float(x) for x in ce.predict(pares, batch_size=self.lote,
                                             show_progress_bar=False)]


def reordenar(consulta: str, candidatos: Sequence[tuple[str, str]],
              reordenador: Reordenador) -> list[tuple[str, float]]:
    """(id, texto) -> (id, pontuacao) do melhor ao pior. Empate mantem a ordem de entrada."""
    if not candidatos:
        return []
    notas = reordenador.pontuar(consulta, [t for _, t in candidatos])
    ordem = sorted(range(len(candidatos)), key=lambda i: (-notas[i], i))
    return [(candidatos[i][0], notas[i]) for i in ordem]
