"""Pool de processos limitado para os compressores.

Os compressores de diff, busca, log e JSON sao Python puro e prendem o GIL. Com
`asyncio.to_thread` as threads disputam o mesmo GIL: na medicao M5, 8 chamadas de
`compress_output` simultaneas seguraram o laco de eventos do daemon por ate 1,4 s
e levaram 22,7 s no total, e o laco atende heartbeat, busca e proxy. Processos
resolvem: o laco so espera um futuro, e as chamadas rodam em paralelo de verdade.

Regras:
- O pool e limitado (`DELEGATION_CORE_COMPRESS_WORKERS`, padrao metade dos
  nucleos, no maximo 4) e sobe so na primeira chamada. `0` desliga e volta ao
  caminho de thread de antes.
- O Kompress nao roda no pool: cada worker carregaria o proprio modelo de cerca
  de 1,5 GB. Texto que o Kompress poderia melhorar cai no caminho em processo,
  onde o modelo fica carregado uma vez.
- Pool quebrado ou sem processo disponivel nao derruba a chamada: ela cai para a
  thread, com aviso no log.
- Prioridade: quem espera um worker entra numa fila por prioridade (`INTERATIVA` antes de
  `LOTE`, por ordem de chegada dentro de cada uma). O `ProcessPoolExecutor` atende por ordem
  de chegada, e uma rajada de lote na frente faria um agente esperar atras dela.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import multiprocessing
import os
import threading
import weakref
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from .. import config
from . import roteador

logger = logging.getLogger("compressao.pool")

_TRAVA = threading.Lock()
_POOL: ProcessPoolExecutor | None = None

#: Quem espera um agente (as ferramentas MCP, o proxy) passa na frente do trabalho em lote.
INTERATIVA, LOTE = 0, 1


class _Portao:
    """Fila por prioridade na frente dos workers. Vive no laco de eventos, sem travas: so o laco a toca."""

    def __init__(self, vagas: int):
        self.vagas = vagas
        self.livres = vagas
        self._fila: list = []
        self._ordem = itertools.count()

    async def entrar(self, prioridade: int) -> None:
        if self.livres > 0 and not self._fila:
            self.livres -= 1
            return
        vez = asyncio.get_running_loop().create_future()
        heapq.heappush(self._fila, (prioridade, next(self._ordem), vez))
        try:
            await vez
        except asyncio.CancelledError:
            # Quem ja recebeu a vaga e foi cancelado antes de usa-la passa a vaga adiante.
            if vez.done() and not vez.cancelled():
                self.sair()
            raise

    def sair(self) -> None:
        while self._fila:
            _, _, vez = heapq.heappop(self._fila)
            if not vez.cancelled():
                vez.set_result(None)
                return
        self.livres += 1

    @property
    def esperando(self) -> int:
        return sum(1 for _, _, v in self._fila if not v.cancelled())


_PORTOES: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _portao(n: int) -> _Portao:
    """O portao do laco de eventos de agora (um por laco: os testes sobem um laco por chamada)."""
    laco = asyncio.get_running_loop()
    p = _PORTOES.get(laco)
    if p is None or p.vagas != n:
        p = _Portao(n)
        _PORTOES[laco] = p
    return p


def workers() -> int:
    """Quantos processos o pool usa; 0 quer dizer sem pool."""
    bruto = os.environ.get("DELEGATION_CORE_COMPRESS_WORKERS", "").strip()
    if bruto:
        try:
            return max(0, int(bruto))
        except ValueError:
            logger.warning("DELEGATION_CORE_COMPRESS_WORKERS invalido: %r", bruto)
    return min(4, max(1, (os.cpu_count() or 2) // 2))


def _trabalho(conteudo: str, contexto: str, tipo: str, bias: float, guardar: bool, config_dir: str) -> dict:
    """O que roda dentro do worker: o roteador, sem o Kompress.

    O worker nasce de um processo novo e nao herda o que o pai reapontou em tempo de execucao. O
    `config_dir` do pai vale aqui tambem, para a guarda (`saidas.sqlite3`) cair no mesmo lugar."""
    from .. import config
    from ..filtros_saida import execucao
    if str(config.CONFIG_DIR) != config_dir:
        config.CONFIG_DIR = Path(config_dir)
        execucao._CON.clear()
    return roteador.comprimir(conteudo, contexto, tipo, bias, guardar, kompress=False)


def _pool(n: int) -> ProcessPoolExecutor:
    global _POOL
    with _TRAVA:
        if _POOL is None:
            _POOL = ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context("forkserver"))
        return _POOL


def _descartar() -> None:
    global _POOL
    with _TRAVA:
        p, _POOL = _POOL, None
    if p is not None:
        p.shutdown(wait=False, cancel_futures=True)


def encerrar() -> None:
    """Fecha o pool, para quem sai e para os testes."""
    _descartar()


def _candidato_a_kompress(r: dict) -> bool:
    return r.get("content_type") == "text" and r.get("compressor") in ("lossless", "none")


async def comprimir(conteudo: str, contexto: str = "", tipo: str = "auto", bias: float = 1.0,
                    guardar: bool = True, kompress: bool = True, prioridade: int = INTERATIVA) -> dict:
    """`roteador.comprimir`, sem segurar o laco de eventos nem o GIL do daemon.

    `prioridade`: quando todos os workers estao ocupados, `INTERATIVA` e atendida antes de `LOTE`."""
    n = workers()
    if n == 0:
        return await asyncio.to_thread(roteador.comprimir, conteudo, contexto, tipo, bias, guardar, kompress)
    portao = _portao(n)
    await portao.entrar(prioridade)
    caiu = False
    try:
        # O ValueError de um `tipo` invalido sai do worker como ele e e tratado pelo chamador.
        r = await asyncio.get_running_loop().run_in_executor(
            _pool(n), _trabalho, conteudo, contexto, tipo, bias, guardar, str(config.CONFIG_DIR))
    except (BrokenProcessPool, OSError, RuntimeError) as e:
        logger.warning("pool de compressores indisponivel (%s: %s); usando thread", type(e).__name__, e)
        _descartar()
        caiu = True
    finally:
        portao.sair()   # a vaga volta antes da queda para a thread, que nao usa worker
    if caiu:
        return await asyncio.to_thread(roteador.comprimir, conteudo, contexto, tipo, bias, guardar, kompress)
    if kompress and _candidato_a_kompress(r):
        # So texto sem outro compressor: o Kompress, que vive neste processo, pode ainda ganhar.
        return await asyncio.to_thread(roteador.comprimir, conteudo, contexto, tipo, bias, guardar, True)
    return r
