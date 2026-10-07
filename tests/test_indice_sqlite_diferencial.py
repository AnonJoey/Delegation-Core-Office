"""A fachada tem que responder o que o ChromaDB responde.

Cada teste faz a mesma operacao nos dois e compara. O Chroma e a referencia
medida em 07/10/2026 (1.5.9); onde ele diverge do que seria razoavel, a fachada
copia o Chroma e o teste diz qual era a surpresa.
"""
import random

import numpy as np
import pytest

chromadb = pytest.importorskip("chromadb")

from delegation_core.indice_sqlite import ClienteSqlite, IndiceSqliteErro  # noqa: E402

D = 16


def _tem_fts() -> bool:
    import sqlite3
    c = sqlite3.connect(":memory:")
    try:
        c.execute("create virtual table t using fts5(x, tokenize='trigram')")
        return True
    except sqlite3.OperationalError:
        return False


precisa_fts = pytest.mark.skipif(not _tem_fts(), reason="este sqlite nao tem FTS5 com trigram")


@pytest.fixture
def par(tmp_path):
    c = chromadb.PersistentClient(path=str(tmp_path / "chroma"),
                                  settings=chromadb.Settings(anonymized_telemetry=False))
    ref = c.get_or_create_collection("col", metadata={"hnsw:space": "cosine"})
    novo = ClienteSqlite(tmp_path / "sqlite").get_or_create_collection(
        "col", metadata={"hnsw:space": "cosine"})
    yield ref, novo
    c.close() if hasattr(c, "close") else None


def _dados(n=300, seed=1):
    rng = random.Random(seed)
    npr = np.random.default_rng(seed)
    v = npr.normal(size=(n, D)).astype(np.float32)
    ids, metas, docs = [], [], []
    for i in range(n):
        ids.append(f"id{i:04d}")
        m = {"kind": rng.choice(["note", "generated", "external"]),
             "folder": rng.choice(["A", "B", "Cc"]), "n": rng.choice([1, 2, 3, 2.5]),
             "ok": rng.choice([True, False])}
        if rng.random() < .3:
            del m["folder"]
        if rng.random() < .1:
            m["extra"] = "x"
        metas.append(m)
        docs.append(f"doc {i}")
    return ids, v.tolist(), metas, docs


def _ambos(par, fn):
    ref, novo = par
    return fn(ref), fn(novo)


WHERES = [
    {"kind": "note"}, {"kind": {"$ne": "note"}}, {"kind": {"$in": ["note", "external"]}},
    {"kind": {"$nin": ["note"]}}, {"folder": "A"}, {"folder": {"$ne": "A"}},
    {"n": 2}, {"n": 2.0}, {"n": "2"}, {"ok": True}, {"ok": 1}, {"n": True},
    {"n": {"$gt": 2}}, {"n": {"$gte": 2}}, {"n": {"$lt": 3}}, {"n": {"$lte": 2}},
    {"zzz": "x"}, {"zzz": {"$ne": "x"}}, {"extra": "x"},
    {"$and": [{"kind": "note"}, {"folder": "B"}]},
    {"$or": [{"kind": "note"}, {"ok": True}]},
    {"$and": [{"kind": {"$ne": "generated"}}, {"$or": [{"folder": "A"}, {"n": {"$gt": 2}}]}]},
    {"kind": {"$eq": "note"}},
]


def test_get_com_cada_filtro_devolve_os_mesmos_ids_na_mesma_ordem(par):
    ids, v, metas, docs = _dados()
    ref, novo = par
    for c in par:
        c.upsert(ids=ids, embeddings=v, metadatas=metas, documents=docs)
    for w in WHERES:
        a, b = _ambos(par, lambda c: c.get(where=w)["ids"])
        assert a == b, f"get(where={w})"
        a, b = _ambos(par, lambda c: c.get(where=w, limit=7, offset=3)["ids"])
        assert a == b, f"get(where={w}, limit, offset)"


def test_query_devolve_os_mesmos_vizinhos_e_distancias(par):
    ids, v, metas, docs = _dados()
    for c in par:
        c.upsert(ids=ids, embeddings=v, metadatas=metas, documents=docs)
    q = np.random.default_rng(9).normal(size=(5, D)).astype(np.float32).tolist()
    for w in [None] + WHERES:
        kw = {"where": w} if w else {}
        a, b = _ambos(par, lambda c: c.query(query_embeddings=q, n_results=10, **kw))
        for i in range(5):
            assert a["ids"][i] == b["ids"][i], f"query(where={w}) consulta {i}"
            assert np.allclose(a["distances"][i], b["distances"][i], atol=1e-4)
            assert a["documents"][i] == b["documents"][i]
            assert a["metadatas"][i] == b["metadatas"][i]


def test_query_com_mais_resultados_que_linhas_e_filtro_vazio(par):
    ids, v, metas, docs = _dados(20)
    for c in par:
        c.upsert(ids=ids, embeddings=v, metadatas=metas, documents=docs)
    q = [v[0]]
    a, b = _ambos(par, lambda c: c.query(query_embeddings=q, n_results=500))
    assert len(a["ids"][0]) == len(b["ids"][0]) == 20
    a, b = _ambos(par, lambda c: c.query(query_embeddings=q, n_results=5, where={"kind": "nada"}))
    assert a["ids"] == b["ids"] == [[]]


def test_get_por_ids_vem_na_ordem_de_armazenamento_e_pula_os_inexistentes(par):
    ids, v, metas, docs = _dados(10)
    for c in par:
        c.upsert(ids=ids, embeddings=v, metadatas=metas, documents=docs)
    a, b = _ambos(par, lambda c: c.get(ids=["id0003", "id0000", "naoexiste"])["ids"])
    assert a == b == ["id0000", "id0003"]


def test_upsert_mescla_metadados_e_mantem_o_documento(par):
    """Surpresa do Chroma: o upsert nao substitui, mescla."""
    for c in par:
        c.upsert(ids=["a"], embeddings=[[1.0] * D], metadatas=[{"k": 1, "j": 2}], documents=["d"])
        c.upsert(ids=["a"], embeddings=[[2.0] * D], metadatas=[{"j": 3, "m": 4}])
    a, b = _ambos(par, lambda c: c.get(ids=["a"]))
    assert a["metadatas"] == b["metadatas"] == [{"k": 1, "j": 3, "m": 4}]
    assert a["documents"] == b["documents"] == ["d"]


def test_update_so_mexe_no_que_existe_e_add_ignora_o_existente(par):
    for c in par:
        c.upsert(ids=["a"], embeddings=[[1.0] * D], metadatas=[{"k": 1}], documents=["d"])
        c.update(ids=["a", "fantasma"], embeddings=[[1.0] * D, [1.0] * D],
                 metadatas=[{"z": 9}, {"z": 9}])
        c.add(ids=["a"], embeddings=[[5.0] * D], metadatas=[{"k": 99}], documents=["outro"])
    a, b = _ambos(par, lambda c: (c.get()["ids"], c.get()["metadatas"], c.get()["documents"]))
    assert a == b == (["a"], [{"k": 1, "z": 9}], ["d"])
    assert par[0].count() == par[1].count() == 1


def test_delete_por_where_por_ids_e_inexistente(par):
    ids, v, metas, docs = _dados(60)
    for c in par:
        c.upsert(ids=ids, embeddings=v, metadatas=metas, documents=docs)
        c.delete(where={"kind": "note"})
        c.delete(ids=["id0001", "naoexiste"])
    a, b = _ambos(par, lambda c: c.get()["ids"])
    assert a == b and "id0001" not in a
    assert par[0].count() == par[1].count()


def test_erros_que_o_chroma_levanta_a_fachada_tambem_levanta(par):
    ref, novo = par
    for c, exc in ((ref, Exception), (novo, IndiceSqliteErro)):
        with pytest.raises(exc):
            c.upsert(ids=["a", "a"], embeddings=[[1.0] * D, [2.0] * D])
        c.upsert(ids=["ok"], embeddings=[[1.0] * D])
        with pytest.raises(exc):
            c.upsert(ids=["dim"], embeddings=[[1.0] * 3])
        with pytest.raises(exc):
            c.get(where={})
        with pytest.raises(exc):
            c.get(where={"a": 1, "b": 2})


def test_get_com_embeddings_devolve_um_array(par):
    for c in par:
        c.upsert(ids=["a", "b"], embeddings=[[1.0] * D, [2.0] * D], documents=["x", "y"])
    a, b = _ambos(par, lambda c: c.get(include=["embeddings"]))
    assert a["embeddings"].shape == b["embeddings"].shape == (2, D)
    assert np.allclose(a["embeddings"], b["embeddings"])
    assert a["documents"] is None and b["documents"] is None


DOCS = ["Relatorio de ESTOURO do bolsao", "relatorio de estouro do bolsao", "nada a ver",
        "ab", "estouro", "O Angelus teve 160h", "dois  espacos"]


def _povoar(par):
    for c in par:
        c.upsert(ids=[f"d{i}" for i in range(len(DOCS))], embeddings=[[float(i + 1)] * D for i in range(len(DOCS))],
                 documents=DOCS, metadatas=[{"i": i} for i in range(len(DOCS))])


@precisa_fts
def test_where_document_igual_ao_chroma(par):
    _povoar(par)
    casos = [{"$contains": "estouro"}, {"$contains": "ESTOURO"}, {"$contains": "ab"},
             {"$contains": "a"}, {"$not_contains": "estouro"}, {"$contains": "dois  esp"},
             {"$and": [{"$contains": "relatorio"}, {"$not_contains": "ESTOURO"}]},
             {"$or": [{"$contains": "Angelus"}, {"$contains": "nada"}]}, {"$contains": "naoexiste"}]
    for wd in casos:
        a, b = _ambos(par, lambda c: c.get(where_document=wd)["ids"])
        assert a == b, f"where_document={wd}"
    a, b = _ambos(par, lambda c: c.query(query_embeddings=[[1.0] * D], n_results=7,
                                         where_document={"$contains": "estouro"})["ids"])
    assert sorted(a[0]) == sorted(b[0])


@precisa_fts
def test_delete_por_where_document(par):
    _povoar(par)
    for c in par:
        c.delete(where_document={"$contains": "estouro"})
    a, b = _ambos(par, lambda c: c.get()["ids"])
    assert a == b


@precisa_fts
def test_buscar_texto_e_hibrida_so_existem_na_fachada(par):
    _povoar(par)
    novo = par[1]
    r = novo.buscar_texto("bolsao estouro", n_results=3)
    assert r["ids"][0] in ("d0", "d1") and len(r["ids"]) == 3 or len(r["ids"]) >= 2
    assert all(s > 0 for s in r["scores"])
    assert novo.buscar_texto("relatorio", where={"i": 1})["ids"] == ["d1"]
    assert novo.buscar_texto("ab")["ids"] == [], "menos de 3 letras nao tem trigrama"
    h = novo.hibrida("estouro", query_embeddings=[[1.0] * D], n_results=3)
    assert len(h["ids"]) == 3 and h["scores"] == sorted(h["scores"], reverse=True)


def test_backup_online_e_um_banco_integro_com_o_mesmo_conteudo(par, tmp_path):
    _povoar(par)
    from delegation_core.indice_sqlite import ClienteSqlite
    cli = par[1]._cliente
    copia = cli.backup(tmp_path / "bk" / "copia.db")
    import shutil
    (tmp_path / "bk2").mkdir()
    shutil.copy(copia, tmp_path / "bk2" / "indice.db")
    reaberto = ClienteSqlite(tmp_path / "bk2")
    assert reaberto.verificar() == "ok"
    assert reaberto.get_collection("col").get()["ids"] == par[1].get()["ids"]
