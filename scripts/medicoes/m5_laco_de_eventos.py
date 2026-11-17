"""Medicao 5: quanto `filter_output` e `compress_output` seguram o laco de eventos do daemon.

Roda as duas ferramentas MCP (a funcao por tras do decorador) dentro de um laco asyncio
com um relogio de 5 ms e mede o maior atraso do relogio, com K chamadas simultaneas.
Atraso do relogio e o tempo que QUALQUER outra requisicao do daemon (inclusive o
heartbeat e o proxy) ficaria esperando.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import time


def saida_grande() -> str:
    return subprocess.run(["ps", "aux"], capture_output=True, text=True).stdout * 8


def diff_grande() -> str:
    """Um diff de 40 arquivos com 400 linhas mudadas em cada: o `compact_diff` tem trabalho a fazer."""
    partes = []
    for i in range(40):
        partes.append(f"diff --git a/src/m{i}.py b/src/m{i}.py\n--- a/src/m{i}.py\n+++ b/src/m{i}.py\n@@ -1,400 +1,400 @@\n")
        partes.append("".join(f"-linha antiga {j} do arquivo {i}\n+linha nova {j} do arquivo {i}\n" for j in range(200)))
    return "".join(partes) * 3


async def relogio(parar: asyncio.Event, atrasos: list):
    while not parar.is_set():
        t = time.perf_counter()
        await asyncio.sleep(0.005)
        atrasos.append(time.perf_counter() - t - 0.005)


async def medir(nome, coro_fn, k):
    atrasos, parar = [], asyncio.Event()
    r = asyncio.create_task(relogio(parar, atrasos))
    await asyncio.sleep(0.05)
    t0 = time.perf_counter()
    await asyncio.gather(*[coro_fn() for _ in range(k)])
    total = time.perf_counter() - t0
    parar.set()
    await r
    return {"ferramenta": nome, "chamadas_simultaneas": k, "total_s": round(total, 2),
            "maior_atraso_do_laco_ms": round(1000 * max(atrasos), 1), "p99_atraso_ms": round(1000 * sorted(atrasos)[int(len(atrasos) * .99) - 1], 1)}


async def principal():
    from delegation_core import server
    fo = getattr(server.filter_output, "fn", server.filter_output)
    co = getattr(server.compress_output, "fn", server.compress_output)
    out = saida_grande()
    diff = diff_grande()
    # linha de base: laco parado
    base = await medir("nada (linha de base)", lambda: asyncio.sleep(0.2), 1)
    res = [base]
    for k in (1, 8):
        res.append(await medir("filter_output ps aux (~%d KB)" % (len(out) // 1024), lambda: fo("ps aux", out, 0), k))
        res.append(await medir("filter_output git diff (~%d KB, modulo portado)" % (len(diff) // 1024),
                               lambda: fo("git diff", diff, 0), k))
        res.append(await medir("compress_output log (~%d KB)" % (len(out) // 1024), lambda: co(out, "", "log"), k))
    for r in res:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(principal())
