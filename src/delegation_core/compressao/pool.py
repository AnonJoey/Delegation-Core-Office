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
import contextvars
import time
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
    """Fila por prioridade na frente dos workers, UMA para o daemon inteiro (6.1.3).

    Ate 23/11/2026 havia um portao por laco de eventos. O proxy roda num laco proprio (uvicorn,
    noutra thread) e o MCP noutro, entao a prioridade de um nunca competia com a do outro: cada
    um tinha a sua fila e as mesmas vagas. Agora o portao e unico e atravessa threads: a trava
    guarda a fila e as vagas, e a vaga chega a quem espera pelo laco dele
    (`call_soon_threadsafe`). Quem desiste, ou cujo laco acabou, passa a vaga adiante."""

    def __init__(self, vagas: int):
        self.vagas = vagas
        self.livres = vagas
        self._fila: list = []
        self._ordem = itertools.count()
        self._trava = threading.Lock()

    async def entrar(self, prioridade: int) -> None:
        laco = asyncio.get_running_loop()
        with self._trava:
            if self.livres > 0 and not self._fila:
                self.livres -= 1
                return
            vez = laco.create_future()
            heapq.heappush(self._fila, (prioridade, next(self._ordem), laco, vez))
        try:
            await vez
        except asyncio.CancelledError:
            # A vaga chegou e a tarefa foi cancelada antes de usa-la: a vaga vai adiante.
            if vez.done() and not vez.cancelled():
                self.sair()
            raise

    def sair(self) -> None:
        while True:
            with self._trava:
                if not self._fila:
                    self.livres += 1
                    return
                _, _, laco, vez = heapq.heappop(self._fila)
            if vez.cancelled():
                continue
            try:
                laco.call_soon_threadsafe(self._dar, vez)
            except RuntimeError:
                continue   # o laco de quem esperava ja fechou: a vaga vai ao proximo
            return

    def _dar(self, vez) -> None:
        """Roda no laco de quem espera. Se ele desistiu nesse meio-tempo, a vaga segue."""
        if vez.cancelled():
            self.sair()
        else:
            vez.set_result(None)

    @property
    def esperando(self) -> int:
        with self._trava:
            return sum(1 for _, _, _, v in self._fila if not v.cancelled())


_PORTAO: _Portao | None = None

#: Onde `comprimir` anota quanto cada chamada esperou por um worker, em segundos. Quem quer saber
#: (o livro, para cada ferramenta MCP; o proxy, para cada pedido) poe uma lista aqui antes e le
#: depois. Lista, e nao numero: a tarefa filha copia o contexto, mas a lista e a mesma.
ESPERAS: contextvars.ContextVar[list | None] = contextvars.ContextVar("espera_do_pool", default=None)


def _portao(n: int) -> _Portao:
    """O portao do daemon. Recriado so quando o numero de workers muda (os testes mudam)."""
    global _PORTAO
    with _TRAVA:
        if _PORTAO is None or _PORTAO.vagas != n:
            _PORTAO = _Portao(n)
        return _PORTAO


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
    # O worker nao grava em `saidas.sqlite3`: junta o que o CCR guardaria e devolve ao daemon,
    # que e o unico escritor (6.1.2). Antes, cada worker abria o arquivo e gravava sozinho.
    execucao._COLETOR = []
    try:
        r = roteador.comprimir(conteudo, contexto, tipo, bias, guardar, kompress=False)
        return {"resultado": r, "ccr": execucao._COLETOR}
    finally:
        execucao._COLETOR = None


def _gravar_do_worker(volta: dict) -> dict:
    """Grava no processo do daemon o que o worker juntou, e devolve o resultado da compressao.

    A ordem importa: o original vai para a guarda ANTES de o texto comprimido, que aponta para
    ele (`Retrieve more: hash=...`), chegar a quem pediu."""
    pendentes = volta.get("ccr") or []
    if pendentes:
        from .ccr import Guarda
        g = Guarda()
        for chave, conteudo in pendentes:
            g.put(chave, conteudo)
    return volta["resultado"]


def _metodo_de_inicio() -> str:
    """`forkserver` onde existe (Linux e macOS); `spawn` no Windows, que so tem esse.

    Os dois partem de um processo limpo, entao o `_trabalho` acima ja recebe o `config_dir` do
    pai por argumento e nao depende de herdar estado. Medido na CI de 17/11/2026: com
    `forkserver` fixo, o Windows dava `cannot find context for 'forkserver'`."""
    return "forkserver" if "forkserver" in multiprocessing.get_all_start_methods() else "spawn"


def _pool(n: int) -> ProcessPoolExecutor:
    global _POOL
    with _TRAVA:
        if _POOL is None:
            _POOL = ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context(_metodo_de_inicio()))
        return _POOL


def _descartar() -> None:
    global _POOL
    with _TRAVA:
        p, _POOL = _POOL, None
    if p is not None:
        p.shutdown(wait=False, cancel_futures=True)


def encerrar() -> None:
    """Fecha o pool e esquece o portao, para quem sai e para os testes."""
    global _PORTAO
    _descartar()
    with _TRAVA:
        _PORTAO = None


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
    t0 = time.monotonic()
    await portao.entrar(prioridade)
    esperas = ESPERAS.get()
    if esperas is not None:
        esperas.append(time.monotonic() - t0)
    caiu = False
    try:
        # O ValueError de um `tipo` invalido sai do worker como ele e e tratado pelo chamador.
        volta = await asyncio.get_running_loop().run_in_executor(
            _pool(n), _trabalho, conteudo, contexto, tipo, bias, guardar, str(config.CONFIG_DIR))
        r = await asyncio.to_thread(_gravar_do_worker, volta)
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
