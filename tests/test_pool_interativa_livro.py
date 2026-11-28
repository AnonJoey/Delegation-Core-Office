"""Portao unico entre lacos, proxy na classe interativa, Kompress no daemon e espera no livro (6.1.3).

Ate 23/11/2026 o portao de prioridade era um por laco de eventos, e o proxy (laco proprio, na
thread do uvicorn) nem passava pelo pool: a prioridade INTERATIVA nunca competia com nada fora
do proprio laco. Estes testes sobem lacos em threads diferentes e conferem a ordem real.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from delegation_core.compressao import pool
from delegation_core.livro import LivroCaixa


@pytest.fixture(autouse=True)
def _pool_limpo(monkeypatch):
    monkeypatch.delenv("DELEGATION_CORE_COMPRESS_WORKERS", raising=False)
    yield
    pool.encerrar()


def _um_worker(monkeypatch, ordem, duracao=0.25, segura=None):
    """`segura` e {conteudo: threading.Event}: esse trabalho ocupa a vaga ate o teste soltar o evento."""
    exec_ = ThreadPoolExecutor(max_workers=1)

    def trabalho(conteudo, contexto, tipo, bias, guardar, config_dir):
        ordem.append(conteudo)
        evento = (segura or {}).get(conteudo)
        if evento is not None:
            evento.wait(30)
        else:
            time.sleep(duracao)
        return {"resultado": {"output": conteudo, "compressor": "none"}, "ccr": []}

    monkeypatch.setenv("DELEGATION_CORE_COMPRESS_WORKERS", "1")
    monkeypatch.setattr(pool, "_pool", lambda n: exec_)
    monkeypatch.setattr(pool, "_trabalho", trabalho)
    return exec_


def _em_outro_laco(coro_fn, *args):
    """Roda `coro_fn(*args)` num laco de eventos novo, noutra thread, como o proxy."""
    caixa = {}

    def alvo():
        caixa["r"] = asyncio.run(coro_fn(*args))

    t = threading.Thread(target=alvo)
    t.start()
    return t, caixa


def _ate(condicao, segundos=20.0):
    """Espera a condicao valer, em vez de dormir um tempo fixo e torcer."""
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicao():
            return
        time.sleep(0.005)
    raise AssertionError("a condicao esperada nao chegou a valer")


def test_interativa_de_outro_laco_passa_na_frente_do_lote_que_espera(monkeypatch):
    """A ordem de chegada era garantida por `time.sleep(0.05)` entre as threads, e o trabalho que ocupava a vaga
    durava 0,25 s. Numa maquina lenta o "agente" entrava na fila depois de a vaga ja ter ido para o "lote", e o
    teste falhava sem defeito nenhum no portao (CI do macOS, 24 e 27/11/2026). Agora cada passo espera o anterior
    acontecer de verdade, e a vaga so e solta com os dois ja na fila."""
    ordem = []
    solta = threading.Event()
    exec_ = _um_worker(monkeypatch, ordem, segura={"ocupa": solta})

    async def lote(nome):
        return await pool.comprimir(nome, prioridade=pool.LOTE, kompress=False)

    async def interativa(nome):
        return await pool.comprimir(nome, prioridade=pool.INTERATIVA, kompress=False)

    def esperando() -> int:
        return pool._PORTAO.esperando if pool._PORTAO is not None else 0

    t1, _ = _em_outro_laco(lote, "ocupa")       # pega a unica vaga
    _ate(lambda: ordem == ["ocupa"])
    t2, _ = _em_outro_laco(lote, "lote")        # espera, noutro laco
    _ate(lambda: esperando() == 1)
    t3, _ = _em_outro_laco(interativa, "agente")  # chega depois, noutro laco, e passa na frente
    _ate(lambda: esperando() == 2)
    solta.set()
    for t in (t1, t2, t3):
        t.join(30)
    exec_.shutdown()
    assert ordem == ["ocupa", "agente", "lote"]


def test_dois_lacos_nao_ganham_vagas_separadas(monkeypatch):
    """Com um portao por laco, cada laco teria a sua vaga e os dois rodariam juntos."""
    ordem, inicios = [], []
    exec_ = ThreadPoolExecutor(max_workers=4)

    def trabalho(conteudo, contexto, tipo, bias, guardar, config_dir):
        inicios.append(time.monotonic())
        ordem.append(conteudo)
        time.sleep(0.25)
        return {"resultado": {"output": conteudo, "compressor": "none"}, "ccr": []}

    monkeypatch.setenv("DELEGATION_CORE_COMPRESS_WORKERS", "1")
    monkeypatch.setattr(pool, "_pool", lambda n: exec_)
    monkeypatch.setattr(pool, "_trabalho", trabalho)

    async def uma(nome):
        return await pool.comprimir(nome, kompress=False)

    ts = [_em_outro_laco(uma, f"c{i}")[0] for i in range(2)]
    for t in ts:
        t.join(10)
    exec_.shutdown()
    assert len(inicios) == 2 and abs(inicios[1] - inicios[0]) >= 0.2, "as duas rodaram ao mesmo tempo"


def test_quem_desiste_em_outro_laco_passa_a_vaga(monkeypatch):
    ordem = []
    exec_ = _um_worker(monkeypatch, ordem)
    resultado = {}

    async def ocupa():
        return await pool.comprimir("ocupa", kompress=False)

    async def desiste():
        tarefa = asyncio.create_task(pool.comprimir("desistente", kompress=False))
        await asyncio.sleep(0.05)
        tarefa.cancel()
        try:
            await tarefa
        except asyncio.CancelledError:
            resultado["cancelada"] = True

    async def depois():
        return await pool.comprimir("depois", kompress=False)

    t1, _ = _em_outro_laco(ocupa)
    time.sleep(0.05)
    t2, _ = _em_outro_laco(desiste)
    time.sleep(0.02)
    t3, c3 = _em_outro_laco(depois)
    for t in (t1, t2, t3):
        t.join(10)
    exec_.shutdown()
    assert resultado.get("cancelada") and ordem == ["ocupa", "depois"]
    assert c3["r"]["output"] == "depois"
    assert pool._portao(1).livres == 1, "a vaga se perdeu"


def test_vaga_oferecida_a_laco_fechado_vai_ao_proximo():
    p = pool._Portao(1)
    p.livres = 0
    morto = asyncio.new_event_loop()
    vez_morta = morto.create_future()
    morto.close()
    p._fila.append((1, 0, morto, vez_morta))

    async def esperar():
        laco = asyncio.get_running_loop()
        vez = laco.create_future()
        with p._trava:
            p._fila.append((1, 1, laco, vez))
        p.sair()
        await asyncio.wait_for(vez, 2)
        return True

    assert asyncio.run(esperar())
    assert p.livres == 0 and not p._fila


def test_espera_fica_anotada_para_quem_pediu(monkeypatch):
    ordem = []
    exec_ = _um_worker(monkeypatch, ordem, duracao=0.3)

    async def cenario():
        esperas: list = []
        a = asyncio.create_task(pool.comprimir("a", kompress=False))
        await asyncio.sleep(0.05)
        pool.ESPERAS.set(esperas)
        await pool.comprimir("b", kompress=False)
        await a
        return esperas

    esperas = asyncio.run(cenario())
    exec_.shutdown()
    assert len(esperas) == 1 and 0.15 < esperas[0] < 1.0


# ── proxy ─────────────────────────────────────────────────────────────────────

def test_proxy_comprime_pelo_pool_na_classe_interativa(monkeypatch, tmp_path):
    import httpx
    from delegation_core.proxy import reescrita
    from delegation_core.proxy.servidor import criar_app
    from starlette.testclient import TestClient

    chamadas = []
    original = pool.comprimir

    async def espiao(conteudo, contexto="", tipo="auto", bias=1.0, guardar=True, kompress=True, prioridade=pool.INTERATIVA):
        chamadas.append((prioridade, kompress, threading.current_thread().name))
        esperas = pool.ESPERAS.get()
        if esperas is not None:
            esperas.append(0.123)
        return await original(conteudo, contexto, tipo, bias, guardar, False, prioridade)

    monkeypatch.setattr(pool, "comprimir", espiao)
    monkeypatch.setattr(reescrita, "_MEMO", reescrita.OrderedDict())
    recebidos = []

    def provedor(req: httpx.Request):
        recebidos.append(json.loads(req.content))
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=httpx.ByteStream(b'{"ok": true}'))

    cfg = SimpleNamespace(proxy_min_chars=2000, proxy_upstream_anthropic="http://provedor",
                          proxy_upstream_openai="http://provedor")
    livro = LivroCaixa(tmp_path / "livro.sqlite3")
    app = criar_app(cfg, livro, cliente_http=httpx.AsyncClient(transport=httpx.MockTransport(provedor)))
    grande = "\n".join(f"src/m{i % 9}.py:{i}:    valor_{i} = calcular({i})  # unico {time.time_ns()}" for i in range(700))
    corpo = {"model": "x", "max_tokens": 5, "messages": [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": grande}]}]}
    with TestClient(app) as c:
        r = c.post("/v1/messages", json=corpo)
    assert r.status_code == 200
    assert chamadas and all(p == pool.INTERATIVA for p, _, _ in chamadas)
    chegou = recebidos[-1]["messages"][0]["content"][0]["content"]
    assert len(chegou) < len(grande)
    linha = livro.relatorio()["ferramentas"][0]
    assert linha["ferramenta"] == "proxy:anthropic" and linha["espera_medida_em"] == 1
    assert linha["espera_p50"] == pytest.approx(0.123)


# ── livro ─────────────────────────────────────────────────────────────────────

def test_livro_antigo_ganha_a_coluna_sem_perder_linhas(tmp_path):
    arq = tmp_path / "livro.sqlite3"
    with sqlite3.connect(arq) as c:
        c.executescript("""
            CREATE TABLE chamadas (em REAL NOT NULL, ferramenta TEXT NOT NULL, cliente TEXT NOT NULL DEFAULT '',
                segundos REAL NOT NULL, chars_entrada INTEGER NOT NULL, chars_saida INTEGER NOT NULL,
                chars_apontados INTEGER NOT NULL DEFAULT 0, erro TEXT NOT NULL DEFAULT '');
            INSERT INTO chamadas VALUES (1.0, 'compress_output', 'cc', 0.5, 10, 5, 0, '');
        """)
    lv = LivroCaixa(arq)
    lv.registrar("compress_output", 0.8, 10, 5, espera=0.4)
    lv.registrar("search_vault", 0.1, 10, 5)
    rel = {f["ferramenta"]: f for f in lv.relatorio()["ferramentas"]}
    assert rel["compress_output"]["chamadas"] == 2
    assert rel["compress_output"]["espera_medida_em"] == 1, "a linha antiga nao tem espera: nulo nao e zero"
    assert rel["compress_output"]["espera_p50"] == 0.4
    assert "espera_p50" not in rel["search_vault"]
    lv.fechar()


def test_middleware_do_livro_registra_a_espera_da_ferramenta(tmp_path, monkeypatch):
    from delegation_core import livro_mcp
    lv = LivroCaixa(tmp_path / "livro.sqlite3")
    monkeypatch.setattr(livro_mcp, "livro", lambda cfg: lv)
    mw = livro_mcp.LivroMiddleware(SimpleNamespace())
    contexto = SimpleNamespace(message=SimpleNamespace(name="compress_output", arguments={"content": "x"}),
                               fastmcp_context=None)

    async def ferramenta_que_comprime(ctx):
        async def filha():
            pool.ESPERAS.get().append(0.25)   # numa tarefa filha, que copia o contexto
        await asyncio.create_task(filha())
        return SimpleNamespace(content=[SimpleNamespace(text="ok")])

    async def ferramenta_sem_fila(ctx):
        return SimpleNamespace(content=[SimpleNamespace(text="ok")])

    asyncio.run(mw.on_call_tool(contexto, ferramenta_que_comprime))
    contexto.message.name = "heartbeat"
    asyncio.run(mw.on_call_tool(contexto, ferramenta_sem_fila))
    rel = {f["ferramenta"]: f for f in lv.relatorio()["ferramentas"]}
    assert rel["compress_output"]["espera_p50"] == 0.25
    assert "espera_p50" not in rel["heartbeat"]
    assert pool.ESPERAS.get() is None, "o middleware tem que devolver o contexto como achou"
    lv.fechar()


# ── Kompress so no daemon ─────────────────────────────────────────────────────

@pytest.mark.parametrize("ligado", [False, True])
def test_shell_kompress_liga_e_desliga_o_kompress_do_daemon(ligado, monkeypatch):
    import http.client
    from http.server import ThreadingHTTPServer
    from delegation_core import dashboard_api
    from delegation_core.filtros_saida import execucao, servico
    from tests._dashboard_auth import AUTH, TOKEN

    visto = {}
    monkeypatch.setattr(servico, "exibir", lambda c, m, s, k, kompress=False: (visto.__setitem__("k", kompress), {"output": s})[1])
    monkeypatch.setattr(dashboard_api, "_cfg", SimpleNamespace(shell_kompress=ligado))
    monkeypatch.setattr(dashboard_api, "_token", TOKEN)
    monkeypatch.setattr(execucao, "_ESCRITOR", True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api._Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        con = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        con.request("POST", "/api/saidas/exibir", body=json.dumps(
            {"comando": "docker ps", "modo": "rota", "saida": "x", "codigo": 0}),
            headers={**AUTH, "Content-Type": "application/json"})
        assert con.getresponse().status == 200
    finally:
        srv.shutdown()
        srv.server_close()
    assert visto["k"] is ligado


def test_worker_do_pool_nunca_carrega_o_kompress(monkeypatch):
    from delegation_core import config
    from delegation_core.compressao import roteador
    pedidos = []
    monkeypatch.setattr(roteador, "_kompress", lambda texto, guarda: pedidos.append(1) or None)
    prosa = ("The deployment finished and the integration suite reported two flaky tests. " * 80)
    pool._trabalho(prosa, "", "text", 1.0, True, str(config.CONFIG_DIR))
    assert pedidos == []


def test_vaga_enviada_a_quem_desistiu_no_meio_do_caminho_segue_adiante():
    """A corrida: a vaga ja foi mandada ao laco de quem esperava, e a tarefa e cancelada antes de
    recebe-la. O `_dar` acha a espera cancelada e tem de passar a vaga, senao ela some."""
    p = pool._Portao(1)

    async def cenario():
        p.livres = 0
        tarefa = asyncio.create_task(p.entrar(pool.INTERATIVA))
        await asyncio.sleep(0)          # a tarefa entra na fila
        p.sair()                        # a vaga sai para ela (agendada no laco)...
        tarefa.cancel()                 # ...e ela desiste antes de o laco entregar
        with pytest.raises(asyncio.CancelledError):
            await tarefa
        await asyncio.sleep(0)
        return p.livres

    assert asyncio.run(cenario()) == 1


def test_middleware_devolve_o_contexto_como_achou(tmp_path, monkeypatch):
    from delegation_core import livro_mcp
    lv = LivroCaixa(tmp_path / "livro.sqlite3")
    monkeypatch.setattr(livro_mcp, "livro", lambda cfg: lv)
    mw = livro_mcp.LivroMiddleware(SimpleNamespace())
    contexto = SimpleNamespace(message=SimpleNamespace(name="x", arguments={}), fastmcp_context=None)

    async def ferramenta(ctx):
        return SimpleNamespace(content=[SimpleNamespace(text="ok")])

    async def cenario():
        de_fora: list = []
        pool.ESPERAS.set(de_fora)
        await mw.on_call_tool(contexto, ferramenta)
        return pool.ESPERAS.get() is de_fora

    assert asyncio.run(cenario())
    lv.fechar()
