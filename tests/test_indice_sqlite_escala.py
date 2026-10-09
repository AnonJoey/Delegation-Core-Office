"""A busca exata nao copia a matriz, e o doctor avisa quando o indice ja pesa.

Medido em 09/10/2026 com 400 mil trechos de 1024 dimensoes: `cache.matriz[idx] @ qn`
copiava a matriz (ou a parte filtrada) a cada consulta. Era 1,6 GB temporario por busca e
a busca sem filtro, que copia tudo, saia mais lenta que a com filtro. Calcular a pontuacao
sobre a matriz inteira e escolher as linhas depois deu 7 vezes menos tempo no p50 (180 ms
para 27 ms) e 1,1 GB a menos de pico, com o mesmo resultado em 900 consultas.
"""
import tracemalloc

import numpy as np
import pytest

from delegation_core import doctor
from delegation_core.indice_sqlite import ClienteSqlite

N, D = 20000, 64
MATRIZ_BYTES = N * D * 4


@pytest.fixture(scope="module")
def colecao(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("escala")
    col = ClienteSqlite(pasta).get_or_create_collection("c", metadata={"hnsw:space": "cosine"})
    rng = np.random.default_rng(3)
    for ini in range(0, N, 5000):
        v = rng.normal(size=(5000, D)).astype(np.float32)
        col.upsert(ids=[f"i{ini + j}" for j in range(5000)], embeddings=v,
                   metadatas=[{"par": (ini + j) % 2 == 0} for j in range(5000)])
    return col, v


@pytest.mark.parametrize("where", [None, {"par": True}])
def test_a_consulta_nao_copia_a_matriz(colecao, where):
    col, _ = colecao
    q = np.random.default_rng(9).normal(size=D).astype(np.float32).tolist()
    col.query(query_embeddings=[q], n_results=5, where=where)       # aquece cache e mascara
    tracemalloc.start()
    try:
        col.query(query_embeddings=[q], n_results=5, where=where)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert pico < MATRIZ_BYTES * 0.25, (
        f"a consulta alocou {pico / 1e6:.1f} MB de pico; a matriz tem {MATRIZ_BYTES / 1e6:.1f} MB. "
        "Indexar a matriz com um vetor de indices copia as linhas escolhidas a cada busca.")


def test_o_resultado_e_o_da_busca_exata_em_numpy(colecao):
    col, _ = colecao
    dados = col.get(include=["embeddings"])
    ids, mat = dados["ids"], np.asarray(dados["embeddings"], dtype=np.float32)
    mat = mat / np.linalg.norm(mat, axis=1, keepdims=True)
    permitido = np.array([i % 2 == 0 for i in range(len(ids))])
    rng = np.random.default_rng(11)
    for _ in range(15):
        q = rng.normal(size=D).astype(np.float32); qn = q / np.linalg.norm(q)
        for onde, mascara in ((None, np.ones(len(ids), bool)), ({"par": True}, permitido)):
            sc = np.where(mascara, mat @ qn, -np.inf)
            esperado = [ids[i] for i in np.argsort(-sc, kind="stable")[:7]]
            obtido = col.query(query_embeddings=[q.tolist()], n_results=7, where=onde)["ids"][0]
            assert obtido == esperado


@pytest.mark.parametrize("linhas,tem_aviso", [(41_000, False), (499_999, False), (500_000, True), (1_200_000, True)])
def test_o_aviso_de_escala_aparece_so_nos_indices_grandes(linhas, tem_aviso):
    texto = doctor.aviso_de_escala_do_indice(linhas)
    assert bool(texto) is tem_aviso
    if tem_aviso:
        assert "GB" in texto and "400 mil" in texto


def test_o_aviso_usa_a_dimensao_do_indice():
    assert "2.0 GB" in doctor.aviso_de_escala_do_indice(500_000, 1024)
    assert "1.5 GB" in doctor.aviso_de_escala_do_indice(500_000, 768)
