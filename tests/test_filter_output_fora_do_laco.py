"""`filter_output` nao segura o laco de eventos do daemon.

O trabalho dele (modulos portados do RTK, filtros TOML, armazem de recuperacao em SQLite) e
sincrono. Rodando no proprio laco, uma saida grande ou um disco lento parava tudo o que o daemon
atende: o heartbeat, o proxy e as outras ferramentas MCP. Aqui o trabalho e simulado por uma
espera de 300 ms (que larga o GIL, como o SQLite), e um relogio de 5 ms mede o maior atraso.
"""

import asyncio
import json
import time

import delegation_core.server as server
from delegation_core.filtros_saida import execucao


def _fn(ferramenta):
    return getattr(ferramenta, "fn", ferramenta)


async def _com_relogio(coro):
    atrasos, parar = [], asyncio.Event()

    async def relogio():
        while not parar.is_set():
            t = time.perf_counter()
            await asyncio.sleep(0.005)
            atrasos.append(time.perf_counter() - t - 0.005)

    tarefa = asyncio.create_task(relogio())
    await asyncio.sleep(0.05)
    resultado = await coro
    parar.set()
    await tarefa
    return resultado, max(atrasos)


def test_o_trabalho_lento_nao_para_o_laco(monkeypatch):
    def lento(f, output, command, exit_code=0, *a, **k):
        time.sleep(0.3)
        return {"output": output, "filter": f.nome, "lossy": False}

    monkeypatch.setattr(execucao, "exibir", lento)
    resposta, atraso = asyncio.run(_com_relogio(_fn(server.filter_output)("ps aux", "linha\n" * 10, 0)))
    assert json.loads(resposta)["filter"] == "ps"
    # O trabalho lento dura 300 ms: travado, o laco para pelo menos isso. 200 ms separa a trava
    # do runner lento (o macOS da CI de 17/11/2026 deu 112 ms sem trava nenhuma).
    assert atraso < 0.2, f"o laco ficou {atraso * 1000:.0f} ms parado"


def test_chamadas_simultaneas_andam_juntas(monkeypatch):
    monkeypatch.setattr(execucao, "exibir", lambda f, o, c, e=0, *a, **k: (time.sleep(0.3), {"output": o, "filter": f.nome, "lossy": False})[1])

    async def oito():
        t0 = time.perf_counter()
        await asyncio.gather(*[_fn(server.filter_output)("ps aux", "x\n", 0) for _ in range(8)])
        return time.perf_counter() - t0

    # Em fila no laco seriam 8 x 0,3 s; em threads, bem menos que isso.
    assert asyncio.run(oito()) < 1.5


def test_o_resultado_nao_mudou():
    r = json.loads(asyncio.run(_fn(server.filter_output)("df -h", "Filesystem Size\n" + "/dev/x 1G\n" * 5, 0)))
    assert "output" in r and r["lossy"] in (True, False)
    assert json.loads(asyncio.run(_fn(server.filter_output)("comando-que-ninguem-conhece", "saida\n", 0))) == {
        "output": "saida\n", "filter": None, "lossy": False}
    git = json.loads(asyncio.run(_fn(server.filter_output)("git status", "On branch x\n\n(use \"git add\")\n", 0)))
    assert git["rtk_module"] == "git/git_cmd" and git["filter"] is None


def test_caso_anotado_ainda_vai_ao_compressor():
    log = "\n".join(f"test tests::caso_{i} ... ok" for i in range(300)) + "\nerror: test failed\n"
    r = json.loads(asyncio.run(_fn(server.filter_output)("cargo test", log, 0)))
    assert r["rtk_module"] == "rust/cargo_cmd" and r["filter"] is None
