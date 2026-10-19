"""Custo do contorno sync_threshold alto: latencia, recall@5, tempo de reabertura e tamanho.

Constroi o mesmo indice (N vetores aleatorios, lotes de 100) com `sync_threshold` 1000
(padrao) e 100000, e mede cada um. O recall e contra a busca exata por produto interno.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from m6_hnsw_concorrencia import DIM, abrir, vetores  # noqa: E402


def medir(sync: int, n: int) -> dict:
    pasta = tempfile.mkdtemp(prefix="m6b_", dir=os.environ.get("MEDICAO_TMP"))
    cam = str(Path(pasta) / "idx")
    v = vetores(n, 1)
    _, col = abrir(cam, sync)
    t0 = time.time()
    for i in range(0, n, 100):
        ids = [str(j) for j in range(i, min(i + 100, n))]
        col.upsert(ids=ids, embeddings=v[i:i + 100].tolist(), documents=ids)
    escrita_s = time.time() - t0
    qs = vetores(200, 7)
    exato = np.argsort(-(qs @ v.T), axis=1)[:, :5]
    lat, acertos = [], 0
    for i, q in enumerate(qs):
        t = time.time()
        r = col.query(query_embeddings=[q.tolist()], n_results=5)
        lat.append(time.time() - t)
        acertos += len({int(x) for x in r["ids"][0]} & set(exato[i].tolist()))
    del col
    t1 = time.time()
    _, col2 = abrir(cam, sync)
    col2.query(query_embeddings=[qs[0].tolist()], n_results=5)
    reabrir_s = time.time() - t1
    tam = sum(f.stat().st_size for f in Path(cam).rglob("*") if f.is_file()) / 1e6
    out = {"sync_threshold": sync, "n": n, "escrita_s": round(escrita_s, 1),
           "consulta_p50_ms": round(1000 * float(np.percentile(lat, 50)), 2),
           "consulta_p99_ms": round(1000 * float(np.percentile(lat, 99)), 2),
           "recall_at_5": round(acertos / (5 * len(qs)), 4), "reabrir_e_consultar_s": round(reabrir_s, 2),
           "pasta_mb": round(tam, 1)}
    shutil.rmtree(pasta, ignore_errors=True)
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
    for sync in (1000, 100000):
        print(json.dumps(medir(sync, n)))
