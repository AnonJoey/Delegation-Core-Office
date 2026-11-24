"""Pool de processos dos compressores: mesmo resultado, laco livre e queda para a thread."""

import asyncio
import importlib
import json
import sys
import time

import pytest

from delegation_core.compressao import pool, roteador

LOG = "".join(
    f"2026-10-16 10:{i % 60:02d}:{i % 60:02d} INFO request handled path=/api/item/{i} status=200 ms={i % 50} "
    f"user=u{i % 97}\n" + (f"2026-10-16 10:00:00 ERROR failed id={i}\n" if i % 400 == 0 else "")
    for i in range(3500))
TEXTO = ("Texto corrido sem cara de log, de diff nem de json, comprido o bastante para passar do "
         "limiar em que o roteador tentaria o compressor de linguagem natural. ") * 300


@pytest.fixture(autouse=True)
def _pool_limpo(monkeypatch):
    monkeypatch.delenv("DELEGATION_CORE_COMPRESS_WORKERS", raising=False)
    yield
    pool.encerrar()


def test_o_resultado_do_pool_e_o_do_roteador_sem_kompress():
    via_pool = asyncio.run(pool.comprimir(LOG, "", "log", kompress=False))
    direto = roteador.comprimir(LOG, "", "log", kompress=False)
    assert via_pool == direto and via_pool["compressor"] == "log"


async def _maior_atraso_do_laco(trabalho, k):
    atrasos, parar = [], asyncio.Event()

    async def relogio():
        while not parar.is_set():
            t = time.perf_counter()
            await asyncio.sleep(0.005)
            atrasos.append(time.perf_counter() - t - 0.005)

    r = asyncio.create_task(relogio())
    await asyncio.sleep(0.05)
    await asyncio.gather(*[trabalho() for _ in range(k)])
    parar.set()
    await r
    return max(atrasos)


def test_o_laco_de_eventos_nao_para_com_varias_chamadas_juntas(monkeypatch):
    """Na medicao M5, 8 chamadas por thread seguraram o laco por 1,4 s: o GIL e dos compressores."""
    # aquece os workers antes de medir: a partida dos processos nao e o que se mede aqui
    asyncio.run(pool.comprimir(LOG[:2000], "", "log", kompress=False))

    async def com_pool():
        return await _maior_atraso_do_laco(lambda: pool.comprimir(LOG, "", "log", kompress=False), 6)

    monkeypatch.setenv("DELEGATION_CORE_COMPRESS_WORKERS", "0")

    async def com_thread():
        return await _maior_atraso_do_laco(lambda: pool.comprimir(LOG, "", "log", kompress=False), 6)

    thread = asyncio.run(com_thread())
    monkeypatch.delenv("DELEGATION_CORE_COMPRESS_WORKERS")
    processo = asyncio.run(com_pool())
    assert processo < 0.25, f"o laco parou {processo:.2f} s mesmo com o pool"
    assert thread > 2 * processo, f"thread {thread:.3f} s contra pool {processo:.3f} s"


def test_o_worker_guarda_o_original_no_mesmo_lugar_que_o_pai():
    """O worker e um processo novo: sem seguir o CONFIG_DIR do pai gravava no estado real."""
    from delegation_core.compressao.ccr import Guarda
    r = asyncio.run(pool.comprimir(LOG, "", "log"))
    assert r["cache_key"] and Guarda().get(r["cache_key"]) == LOG


def test_texto_que_o_kompress_pode_melhorar_roda_no_processo_do_daemon(monkeypatch):
    """O modelo do Kompress tem ~1,5 GB: um por worker seria um por processo. Fica onde ja esta carregado."""
    chamadas = []
    monkeypatch.setattr(roteador, "_kompress", lambda texto, guarda: chamadas.append(len(texto)) or None)
    asyncio.run(pool.comprimir(TEXTO, "", "text"))
    assert len(chamadas) == 1


def test_log_nao_passa_pelo_kompress_nem_no_processo_do_daemon(monkeypatch):
    chamadas = []
    monkeypatch.setattr(roteador, "_kompress", lambda texto, guarda: chamadas.append(1) or None)
    r = asyncio.run(pool.comprimir(LOG, "", "log"))
    assert r["compressor"] == "log" and chamadas == []


def test_pool_quebrado_cai_para_a_thread_sem_derrubar_a_chamada(monkeypatch):
    from concurrent.futures.process import BrokenProcessPool

    class Quebrado:
        def submit(self, *a, **k):
            raise BrokenProcessPool("morreu")

        def shutdown(self, *a, **k):
            pass

    monkeypatch.setattr(pool, "_POOL", Quebrado())
    r = asyncio.run(pool.comprimir(LOG, "", "log", kompress=False))
    assert r["compressor"] == "log"
    assert pool._POOL is None


def test_workers_zero_desliga_o_pool(monkeypatch):
    monkeypatch.setenv("DELEGATION_CORE_COMPRESS_WORKERS", "0")
    r = asyncio.run(pool.comprimir(LOG, "", "log", kompress=False))
    assert r["compressor"] == "log" and pool._POOL is None


def test_tipo_invalido_levanta_valueerror_como_o_roteador():
    with pytest.raises(ValueError):
        asyncio.run(pool.comprimir(LOG, "", "nao-existe"))


def test_a_ferramenta_compress_output_usa_o_pool():
    from delegation_core import server
    fn = getattr(server.compress_output, "fn", server.compress_output)
    r = json.loads(asyncio.run(fn(LOG, "", "log")))
    assert r["compressor"] == "log"


def test_importar_o_main_como_modulo_nao_roda_o_daemon(monkeypatch):
    """Os workers do pool reimportam o modulo principal; sem o guarda cada um subiria outro daemon."""
    from delegation_core import cli
    monkeypatch.setattr(cli, "main", lambda *a, **k: pytest.fail("main() rodou na importacao"))
    sys.modules.pop("delegation_core.__main__", None)
    importlib.import_module("delegation_core.__main__")


# ── prioridade: INTERATIVA antes de LOTE quando todos os workers estao ocupados ──────────────────

def _falso_pool(monkeypatch, ordem, duracao=0.15):
    """Um unico worker (thread) que anota a ordem em que o trabalho chega a ele."""
    from concurrent.futures import ThreadPoolExecutor
    exec_ = ThreadPoolExecutor(max_workers=1)

    def trabalho(conteudo, contexto, tipo, bias, guardar, config_dir):
        ordem.append(conteudo)
        time.sleep(duracao)
        # O contrato do worker desde o 6.1.2: o resultado e o que a guarda reversivel juntou.
        return {"resultado": {"output": conteudo}, "ccr": []}

    monkeypatch.setenv("DELEGATION_CORE_COMPRESS_WORKERS", "1")
    monkeypatch.setattr(pool, "_pool", lambda n: exec_)
    monkeypatch.setattr(pool, "_trabalho", trabalho)
    return exec_


def test_interativa_passa_na_frente_do_lote_que_esta_esperando(monkeypatch):
    ordem = []
    exec_ = _falso_pool(monkeypatch, ordem)

    async def cenario():
        a = asyncio.create_task(pool.comprimir("lote-a", prioridade=pool.LOTE, kompress=False))
        await asyncio.sleep(0.03)          # lote-a ja esta no worker
        b = asyncio.create_task(pool.comprimir("lote-b", prioridade=pool.LOTE, kompress=False))
        c = asyncio.create_task(pool.comprimir("lote-c", prioridade=pool.LOTE, kompress=False))
        await asyncio.sleep(0.01)
        i = asyncio.create_task(pool.comprimir("interativa", prioridade=pool.INTERATIVA, kompress=False))
        await asyncio.gather(a, b, c, i)

    asyncio.run(cenario())
    exec_.shutdown()
    assert ordem == ["lote-a", "interativa", "lote-b", "lote-c"]


def test_mesma_prioridade_segue_a_ordem_de_chegada(monkeypatch):
    ordem = []
    exec_ = _falso_pool(monkeypatch, ordem, duracao=0.05)

    async def cenario():
        tarefas = []
        for nome in ("a", "b", "c", "d"):
            tarefas.append(asyncio.create_task(pool.comprimir(nome, kompress=False)))
            await asyncio.sleep(0.005)
        await asyncio.gather(*tarefas)

    asyncio.run(cenario())
    exec_.shutdown()
    assert ordem == ["a", "b", "c", "d"]


def test_a_prioridade_padrao_e_interativa(monkeypatch):
    ordem = []
    exec_ = _falso_pool(monkeypatch, ordem)

    async def cenario():
        a = asyncio.create_task(pool.comprimir("ocupa", prioridade=pool.LOTE, kompress=False))
        await asyncio.sleep(0.03)
        b = asyncio.create_task(pool.comprimir("lote", prioridade=pool.LOTE, kompress=False))
        c = asyncio.create_task(pool.comprimir("padrao", kompress=False))
        await asyncio.gather(a, b, c)

    asyncio.run(cenario())
    exec_.shutdown()
    assert ordem == ["ocupa", "padrao", "lote"]


def test_quem_desiste_da_fila_nao_perde_a_vaga_dos_outros(monkeypatch):
    ordem = []
    exec_ = _falso_pool(monkeypatch, ordem)

    async def cenario():
        a = asyncio.create_task(pool.comprimir("a", kompress=False))
        await asyncio.sleep(0.03)
        b = asyncio.create_task(pool.comprimir("b", kompress=False))
        c = asyncio.create_task(pool.comprimir("c", kompress=False))
        await asyncio.sleep(0.01)
        b.cancel()
        await asyncio.gather(a, c)
        with pytest.raises(asyncio.CancelledError):
            await b
        # Depois de tudo, o portao volta a ter a vaga inteira.
        return pool._portao(1).livres

    livres = asyncio.run(cenario())
    exec_.shutdown()
    assert ordem == ["a", "c"] and livres == 1


def test_o_portao_so_conta_quem_ainda_espera():
    async def cenario():
        p = pool._Portao(1)
        await p.entrar(pool.INTERATIVA)
        esperas = [asyncio.create_task(p.entrar(pool.LOTE)) for _ in range(3)]
        await asyncio.sleep(0.01)
        assert p.esperando == 3
        esperas[1].cancel()
        await asyncio.sleep(0.01)
        assert p.esperando == 2
        p.sair()
        await asyncio.sleep(0.01)
        assert p.esperando == 1 and p.livres == 0
        for e in esperas:
            e.cancel()
        await asyncio.gather(*esperas, return_exceptions=True)

    asyncio.run(cenario())
