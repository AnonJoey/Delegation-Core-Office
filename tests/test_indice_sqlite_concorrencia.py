"""Varios processos, kill -9 e um leitor de vida longa: o que o Chroma nao aguenta."""
import os
import random
import subprocess
import sys
import time

import numpy as np

from delegation_core.indice_sqlite import ClienteSqlite

D = 16
LOTE = 20

ESCRITOR = r"""
import sys, time, numpy as np
from delegation_core.indice_sqlite import ClienteSqlite
pasta, wid, log = sys.argv[1], sys.argv[2], sys.argv[3]
col = ClienteSqlite(pasta).get_or_create_collection("c", metadata={"hnsw:space": "cosine"})
rng = np.random.default_rng(int(wid) + 1)
lote = 0
while True:
    v = rng.normal(size=(%d, %d)).astype(np.float32)
    ids = [f"w{wid}-{lote}-{i}" for i in range(%d)]
    col.upsert(ids=ids, embeddings=v, metadatas=[{"w": wid, "lote": lote}] * %d, documents=["x"] * %d)
    with open(log, "a") as f:
        f.write(f"{lote}\n"); f.flush()
    lote += 1
    time.sleep(0.01)
""" % (LOTE, D, LOTE, LOTE, LOTE)


def _lotes(col):
    por = {}
    for i in col.get(include=[])["ids"]:
        k = i.rsplit("-", 1)[0]
        por[k] = por.get(k, 0) + 1
    return por


def test_escritores_mortos_com_kill9_nao_deixam_lote_pela_metade(tmp_path):
    pasta = tmp_path / "idx"
    leitor = ClienteSqlite(pasta).get_or_create_collection("c", metadata={"hnsw:space": "cosine"})
    leitor.upsert(ids=["base"], embeddings=[[1.0] * D])
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    logs = {w: tmp_path / f"log{w}" for w in range(100, 120)}
    vivos: dict[int, subprocess.Popen] = {}

    def lanca(w):
        vivos[w] = subprocess.Popen([sys.executable, "-c", ESCRITOR, str(pasta), str(w), str(logs[w])], env=env)

    proximo = 100
    for _ in range(4):
        lanca(proximo); proximo += 1
    rng = random.Random(4)
    # O laco termina pelo que o teste precisa ver, nao pelo relogio. Com 8 s fixos e
    # as mortes sorteadas a cada volta, um runner lento (o Windows do CI: subir um
    # processo Python com numpy leva segundos) dava menos de tres voltas e o teste
    # falhava com "o teste nao matou ninguem" sem defeito nenhum no indice. O teto
    # existe so para nao pendurar o CI se algo travar de verdade.
    teto = time.time() + 90
    mortes = 0
    leituras = 0

    def confirmados_ate_agora() -> int:
        return sum(len(lg.read_text().split()) for lg in logs.values() if lg.exists())

    while time.time() < teto:
        time.sleep(0.4)
        leituras += leitor.count()                    # o leitor segue sincronizando
        assert leitor.query(query_embeddings=[[1.0] * D], n_results=3)["ids"][0]
        if rng.random() < 0.6 and proximo < 120:
            w = rng.choice(list(vivos))
            vivos.pop(w).kill()
            mortes += 1
            lanca(proximo); proximo += 1
        if mortes >= 6 and confirmados_ate_agora() > 40:
            break
    for p in vivos.values():
        p.kill()
    for p in list(vivos.values()):
        p.wait()
    assert mortes >= 3, f"o teste nao matou ninguem ({mortes} mortes em 90 s)"

    novo = ClienteSqlite(pasta)
    assert novo.verificar() == "ok"
    fresco = novo.get_collection("c")
    por = _lotes(fresco)
    meio = {k: n for k, n in por.items() if k != "base" and n != LOTE}
    assert not meio, f"lotes pela metade: {meio}"
    confirmados = {(w, int(x)) for w, lg in logs.items() if lg.exists() for x in lg.read_text().split()}
    sumidos = [(w, l) for w, l in confirmados if por.get(f"w{w}-{l}") != LOTE]
    assert not sumidos, f"lotes confirmados que sumiram: {sumidos[:5]}"
    assert len(confirmados) > 20
    # o cache incremental do leitor de vida longa == uma carga completa
    assert leitor.get(include=[])["ids"] == fresco.get(include=[])["ids"]
    q = np.random.default_rng(0).normal(size=D).tolist()
    assert leitor.query(query_embeddings=[q], n_results=10)["ids"] == fresco.query(query_embeddings=[q], n_results=10)["ids"]


def test_cenario_longevo_do_m6_um_segura_aberto_outro_abre_escreve_e_sai(tmp_path):
    """Onde o ChromaDB 1.5.9 perdeu 6.700 de 41.000 linhas e 7 de 10 processos cairam."""
    pasta = tmp_path / "idx"
    a = ClienteSqlite(pasta).get_or_create_collection("c", metadata={"hnsw:space": "cosine"})
    base = np.random.default_rng(1).normal(size=(500, D)).astype(np.float32)
    a.upsert(ids=[f"b{i}" for i in range(500)], embeddings=base)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    codigo = (
        "import sys, numpy as np\n"
        "from delegation_core.indice_sqlite import ClienteSqlite\n"
        "c = ClienteSqlite(sys.argv[1]).get_or_create_collection('c', metadata={'hnsw:space': 'cosine'})\n"
        "k = int(sys.argv[2]); v = np.random.default_rng(k).normal(size=(1200, %d)).astype(np.float32)\n"
        "c.upsert(ids=[f'p{k}-{i}' for i in range(1200)], embeddings=v)\n" % D)
    for ciclo in range(10):
        p = subprocess.run([sys.executable, "-c", codigo, str(pasta), str(ciclo)], env=env,
                           capture_output=True, text=True)
        assert p.returncode == 0, p.stderr[-300:]
        assert a.count() == 500 + (ciclo + 1) * 1200, f"o processo aberto nao viu o ciclo {ciclo}"


def test_poda_do_registro_obriga_recarga_completa_sem_perder_nada(tmp_path, monkeypatch):
    from delegation_core import indice_sqlite as m
    monkeypatch.setattr(m, "MUDANCAS_MAXIMAS", 50)
    pasta = tmp_path / "idx"
    a = ClienteSqlite(pasta).get_or_create_collection("c", metadata={"hnsw:space": "cosine"})
    a.upsert(ids=["x"], embeddings=[[1.0] * D])
    outro = ClienteSqlite(pasta).get_collection("c")
    for lote in range(30):                                   # bem alem do limite de 50
        outro.upsert(ids=[f"l{lote}-{i}" for i in range(10)], embeddings=np.ones((10, D), dtype=np.float32))
    assert a.count() == 301
    outro.delete(where={"zz": 1}) if False else None
    outro.delete(ids=["x"])
    assert a.count() == 300 and "x" not in a.get(include=[])["ids"]


def test_atualizacao_de_linha_existente_por_outro_processo_chega_ao_leitor(tmp_path):
    """O cache so aplica a mudanca se o upsert de uma linha existente tambem for registrado."""
    pasta = tmp_path / "idx"
    a = ClienteSqlite(pasta).get_or_create_collection("c", metadata={"hnsw:space": "cosine"})
    a.upsert(ids=["x", "y"], embeddings=[[1.0] + [0.0] * (D - 1), [0.0, 1.0] + [0.0] * (D - 2)],
             metadatas=[{"v": 1}, {"v": 1}], documents=["antigo", "outro"])
    assert a.query(query_embeddings=[[1.0] + [0.0] * (D - 1)], n_results=1)["ids"][0] == ["x"]
    b = ClienteSqlite(pasta).get_collection("c")
    # x passa a apontar para o eixo 2 e ganha metadado novo; y passa a apontar para o eixo 1
    b.upsert(ids=["x"], embeddings=[[0.0, 1.0] + [0.0] * (D - 2)], metadatas=[{"v": 2}], documents=["novo"])
    b.upsert(ids=["y"], embeddings=[[1.0] + [0.0] * (D - 1)])
    r = a.query(query_embeddings=[[1.0] + [0.0] * (D - 1)], n_results=1)
    assert r["ids"][0] == ["y"], "a matriz do leitor ficou com o vetor antigo"
    assert a.get(ids=["x"])["metadatas"] == [{"v": 2}]
    assert a.get(ids=["x"])["documents"] == ["novo"]
    assert a.get(where={"v": 2})["ids"] == ["x"], "a mascara em cache ficou com o metadado antigo"


def test_falha_no_meio_do_lote_desfaz_tudo_e_nao_deixa_a_conexao_presa(tmp_path):
    col = ClienteSqlite(tmp_path / "idx").get_or_create_collection("c", metadata={"hnsw:space": "cosine"})
    col.upsert(ids=["base"], embeddings=[[1.0] * D])
    nao_serializavel = {"quebra": object()}
    import pytest
    with pytest.raises(TypeError):
        col.upsert(ids=["a", "b", "c"], embeddings=[[1.0] * D] * 3,
                   metadatas=[{"ok": 1}, nao_serializavel, {"ok": 3}])
    assert col.count() == 1 and col.get(ids=["a"])["ids"] == [], "o lote ficou pela metade"
    col.upsert(ids=["depois"], embeddings=[[2.0] * D])          # a conexao nao ficou em transacao
    assert col.count() == 2
