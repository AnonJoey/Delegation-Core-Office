"""Medicao 6 (e 17b): leitura e escrita concorrentes no HNSW do ChromaDB.

Reproduz a forma do relato (indice de ~17 mil vetores, escrita em lotes que
cruzam o `sync_threshold`) em tres arranjos e diz o que quebrou:

  threads     um processo, 1 escritor e N leitores no mesmo PersistentClient
  leitor      dois processos: o escritor e um leitor com cliente proprio
  escritores  dois processos escrevendo na mesma pasta (o daemon e a CLI)
  sequencial  controle do longevo: so o B, 10 vezes, SEM nenhum processo segurando o indice aberto
  longevo     o processo A fica com o cliente aberto (o daemon) e, entre as escritas
              dele, o processo B (a CLI ou o hook) abre, escreve e sai. Repete 10 ciclos.

Vetores aleatorios normalizados: o relato nao reproduziu assim, entao um
resultado "nao quebrou" aqui NAO prova que o fluxo real e seguro.
Uso: m6_hnsw_concorrencia.py {threads|leitor|escritores} [--sync N] [--base N] [--extra N]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

DIM = 768


def vetores(n: int, seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal((n, DIM)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def abrir(caminho: str, sync: int):
    import chromadb
    from chromadb.api.collection_configuration import UpdateCollectionConfiguration
    from chromadb.api.collection_configuration import UpdateHNSWConfiguration
    c = chromadb.PersistentClient(path=caminho)
    col = c.get_or_create_collection("vault", metadata={"hnsw:space": "cosine"})
    if sync != 1000:
        col.modify(configuration=UpdateCollectionConfiguration(hnsw=UpdateHNSWConfiguration(sync_threshold=sync)))
    return c, col


def escrever(caminho: str, sync: int, prefixo: str, n: int, lote: int, seed: int, saida: mp.Queue | None = None):
    erro = None
    t0 = time.time()
    try:
        _, col = abrir(caminho, sync)
        v = vetores(n, seed)
        for i in range(0, n, lote):
            ids = [f"{prefixo}{j}" for j in range(i, min(i + lote, n))]
            col.upsert(ids=ids, embeddings=v[i:i + lote].tolist(), documents=ids)
    except Exception as e:  # noqa: BLE001
        erro = f"{type(e).__name__}: {str(e)[:200]}"
    if saida is not None:
        saida.put({"quem": prefixo, "erro": erro, "s": round(time.time() - t0, 1)})
    return erro


def ler(caminho: str, sync: int, parar: mp.Event, saida: mp.Queue, nome: str):
    erros, ok, lat = [], 0, []
    try:
        _, col = abrir(caminho, sync)
        q = vetores(1, 99)[0].tolist()
        while not parar.is_set():
            t = time.time()
            try:
                r = col.query(query_embeddings=[q], n_results=5)
                ok += 1
                lat.append(time.time() - t)
                assert len(r["ids"][0]) > 0
            except Exception as e:  # noqa: BLE001
                erros.append(f"{type(e).__name__}: {str(e)[:160]}")
                time.sleep(0.05)
    except Exception as e:  # noqa: BLE001
        erros.append(f"abrir: {type(e).__name__}: {str(e)[:160]}")
    saida.put({"quem": nome, "consultas": ok, "erros": len(erros), "amostra_erros": erros[:3],
               "p50_ms": round(1000 * float(np.percentile(lat, 50)), 1) if lat else None,
               "p99_ms": round(1000 * float(np.percentile(lat, 99)), 1) if lat else None})


def tamanho_link_lists(caminho: str) -> dict:
    out = {}
    for p in Path(caminho).rglob("link_lists.bin"):
        out[p.parent.name[:8]] = p.stat().st_size
    return out


def principal() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["threads", "leitor", "escritores", "longevo", "sequencial"])
    ap.add_argument("--sync", type=int, default=1000)
    ap.add_argument("--base", type=int, default=17000)
    ap.add_argument("--extra", type=int, default=3000)
    a = ap.parse_args()

    pasta = tempfile.mkdtemp(prefix="m6_", dir=os.environ.get("MEDICAO_TMP"))
    caminho = str(Path(pasta) / "idx")
    t0 = time.time()
    erro_base = escrever(caminho, a.sync, "base", a.base, 500, 1)
    base_s = round(time.time() - t0, 1)
    ctx = mp.get_context("spawn")
    fila, parar = ctx.Queue(), ctx.Event()
    resultado = {"modo": a.modo, "sync_threshold": a.sync, "base": a.base, "extra": a.extra,
                 "base_s": base_s, "erro_base": erro_base}
    codigos = {}

    if a.modo in ("longevo", "sequencial"):
        import subprocess
        col = abrir(caminho, a.sync)[1] if a.modo == "longevo" else None
        ciclos, lote = 10, 1200
        erros, nao_viu_b = [], 0
        for k in range(ciclos):
            r = subprocess.run([sys.executable, __file__, "_b", caminho, str(a.sync), f"B{k}_", str(lote), str(100 + k)],
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                erros.append(f"B{k} saiu {r.returncode}: {r.stderr[-160:]}")
            if col is None:
                continue
            try:
                achou = col.get(ids=[f"B{k}_0"])["ids"]
                nao_viu_b += 0 if achou else 1
                v = vetores(lote, 200 + k)
                col.upsert(ids=[f"A{k}_{j}" for j in range(lote)], embeddings=v.tolist(),
                           documents=[f"A{k}_{j}" for j in range(lote)])
                col.query(query_embeddings=[vetores(1, 99)[0].tolist()], n_results=5)
            except Exception as e:  # noqa: BLE001
                erros.append(f"A ciclo {k}: {type(e).__name__}: {str(e)[:200]}")
        resultado.update(ciclos=ciclos, lote=lote, esperado=a.base + ciclos * (2 if col is not None else 1) * lote, erros=erros[:6],
                         n_erros=len(erros), a_nao_viu_escrita_do_b=nao_viu_b)
    elif a.modo == "threads":
        _, col = abrir(caminho, a.sync)
        pare = threading.Event()
        stats = {"ok": 0, "err": []}

        def leitor():
            q = vetores(1, 99)[0].tolist()
            while not pare.is_set():
                try:
                    col.query(query_embeddings=[q], n_results=5)
                    stats["ok"] += 1
                except Exception as e:  # noqa: BLE001
                    stats["err"].append(f"{type(e).__name__}: {str(e)[:160]}")
        ths = [threading.Thread(target=leitor) for _ in range(4)]
        for t in ths:
            t.start()
        ew = escrever(caminho, a.sync, "extra", a.extra, 100, 2)
        pare.set()
        for t in ths:
            t.join()
        resultado.update(erro_escrita=ew, consultas=stats["ok"], erros_leitura=len(stats["err"]),
                         amostra_erros=stats["err"][:3])
    else:
        leitores = []
        if a.modo == "leitor":
            p = ctx.Process(target=ler, args=(caminho, a.sync, parar, fila, "leitor"))
            p.start()
            leitores.append(p)
        escritores = [ctx.Process(target=escrever, args=(caminho, a.sync, "extraA", a.extra, 100, 2, fila))]
        if a.modo == "escritores":
            escritores.append(ctx.Process(target=escrever, args=(caminho, a.sync, "extraB", a.extra, 100, 3, fila)))
        for p in escritores:
            p.start()
        for p in escritores:
            p.join(timeout=600)
            codigos[p.pid] = p.exitcode
            if p.is_alive():
                p.kill()
        parar.set()
        for p in leitores:
            p.join(timeout=30)
            codigos[p.pid] = p.exitcode
        msgs = []
        while not fila.empty():
            msgs.append(fila.get())
        resultado["processos"] = msgs
        resultado["codigos_de_saida"] = list(codigos.values())

    try:
        _, col = abrir(caminho, a.sync)
        resultado["contagem_final"] = col.count()
        r = col.query(query_embeddings=[vetores(1, 99)[0].tolist()], n_results=5)
        resultado["consulta_final_ok"] = len(r["ids"][0]) == 5
    except Exception as e:  # noqa: BLE001
        resultado["abrir_depois"] = f"{type(e).__name__}: {str(e)[:200]}"
    resultado["link_lists_bytes"] = tamanho_link_lists(caminho)
    resultado["tamanho_pasta_mb"] = round(sum(f.stat().st_size for f in Path(caminho).rglob("*") if f.is_file()) / 1e6, 1)
    print(json.dumps(resultado, ensure_ascii=False))
    shutil.rmtree(pasta, ignore_errors=True)
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "_b":
        _, _, cam, sy, pre, n, seed = sys.argv
        e = escrever(cam, int(sy), pre, int(n), 100, int(seed))
        sys.exit(1 if e else 0)
    sys.exit(principal())
