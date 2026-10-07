"""A migracao Chroma -> SQLite nao pode perder, alterar nem trocar nada em silencio."""
import json
import os
import sqlite3

import numpy as np
import pytest

chromadb = pytest.importorskip("chromadb")

from delegation_core import migracao_indice as mig  # noqa: E402
from delegation_core.config import Config  # noqa: E402
from delegation_core.indice_sqlite import ClienteSqlite  # noqa: E402

D = 8


def _chroma(tmp_path, n=120):
    pasta = tmp_path / "chroma"
    c = chromadb.PersistentClient(path=str(pasta), settings=chromadb.Settings(anonymized_telemetry=False))
    col = c.get_or_create_collection("vault_x", metadata={"hnsw:space": "cosine"})
    v = np.random.default_rng(3).normal(size=(n, D)).astype(np.float32)
    col.upsert(ids=[f"n{i}" for i in range(n)], embeddings=v.tolist(),
               documents=[f"texto com acento: coração {i}" for i in range(n)],
               metadatas=[{"kind": "note" if i % 2 else "generated", "i": i, "ok": bool(i % 3)} for i in range(n)])
    legado = c.get_or_create_collection("vault_bge", metadata={"hnsw:space": "cosine"})
    legado.upsert(ids=["a"], embeddings=[[1.0] * 4], documents=["legado"])
    del c
    return pasta


@pytest.fixture
def cfg(tmp_path):
    return Config(vault_path=str(tmp_path / "vault"))


def test_migra_todas_as_colecoes_e_o_resultado_e_identico(tmp_path, cfg):
    origem = _chroma(tmp_path)
    destino = tmp_path / "vault" / ".indice_sqlite"
    r = mig.migrar(cfg, origem=origem, destino=destino, amostra=10, pasta_de_trabalho=tmp_path / "t")
    assert r["ok"] and r["verificacao"]["ok"]
    assert sorted(r["importado"]) == ["vault_bge", "vault_x"]
    novo = ClienteSqlite(destino)
    col = novo.get_collection("vault_x")
    ref = chromadb.PersistentClient(path=str(origem), settings=chromadb.Settings(anonymized_telemetry=False)).get_collection("vault_x")
    a = ref.get(include=["documents", "metadatas", "embeddings"])
    b = col.get(include=["documents", "metadatas", "embeddings"])
    assert a["ids"] == b["ids"] and a["documents"] == b["documents"] and a["metadatas"] == b["metadatas"]
    assert np.array_equal(np.asarray(a["embeddings"]), b["embeddings"])
    assert (destino / "migracao.json").exists()


def test_o_conteudo_do_chroma_de_origem_nao_muda(tmp_path, cfg):
    """Comparado pelo conteudo: abrir o Chroma regrava arquivos dele (medido), entao
    byte a byte nao serve. O que a migracao promete e nao escrever linha nenhuma la."""
    origem = _chroma(tmp_path)

    def foto():
        c = chromadb.PersistentClient(path=str(origem), settings=chromadb.Settings(anonymized_telemetry=False))
        out = {}
        for info in c.list_collections():
            g = c.get_collection(info.name).get(include=["documents", "metadatas", "embeddings"])
            out[info.name] = (g["ids"], g["documents"], g["metadatas"], np.asarray(g["embeddings"]).tobytes())
        return out

    antes = foto()
    mig.migrar(cfg, origem=origem, destino=tmp_path / "d", amostra=5, pasta_de_trabalho=tmp_path / "t")
    assert foto() == antes


@pytest.mark.parametrize("estrago,esperado", [
    ("UPDATE chunks SET doc='adulterado' WHERE rid=5", "documento"),
    ("UPDATE chunks SET meta='{\"kind\": \"outro\"}' WHERE rid=6", "metadados"),
    ("UPDATE chunks SET vec=zeroblob(length(vec)) WHERE rid=7", "vetor"),
    ("DELETE FROM chunks WHERE rid=8", "contagem"),
])
def test_o_verificador_pega_cada_tipo_de_estrago(tmp_path, cfg, estrago, esperado):
    origem = _chroma(tmp_path)
    export = tmp_path / "export"
    mig.exportar_em_filho(origem, export, amostra=5)
    alvo = tmp_path / "alvo"
    mig.importar(export, alvo)
    assert mig.verificar(export, alvo)["ok"]
    c = sqlite3.connect(alvo / "indice.db")
    c.execute(estrago); c.commit(); c.close()
    rel = mig.verificar(export, alvo)
    assert rel["ok"] is False
    assert esperado in json.dumps(rel["colecoes"]["vault_x"]["problemas"])


def test_verificacao_que_falha_nao_troca_o_destino(tmp_path, cfg, monkeypatch):
    origem = _chroma(tmp_path)
    destino = tmp_path / "d"
    destino.mkdir()
    (destino / "marca.txt").write_text("destino anterior")
    monkeypatch.setattr(mig, "verificar", lambda *a, **k: {"ok": False, "colecoes": {}})
    with pytest.raises(RuntimeError, match="NAO foi trocado"):
        mig.migrar(cfg, origem=origem, destino=destino, amostra=5, pasta_de_trabalho=tmp_path / "t")
    assert (destino / "marca.txt").read_text() == "destino anterior"
    assert not list(tmp_path.glob("d.novo-*")), "a pasta temporaria ficou para tras"


def test_destino_existente_e_guardado_ao_lado_nunca_apagado(tmp_path, cfg):
    origem = _chroma(tmp_path)
    destino = tmp_path / "d"
    destino.mkdir()
    (destino / "marca.txt").write_text("v1")
    r = mig.migrar(cfg, origem=origem, destino=destino, amostra=5, pasta_de_trabalho=tmp_path / "t")
    assert (tmp_path / r["destino_anterior"].split("/")[-1] / "marca.txt").read_text() == "v1"
    assert (destino / "indice.db").exists()


def test_chroma_que_nao_abre_vira_erro_claro_e_nada_muda(tmp_path, cfg):
    origem = tmp_path / "quebrado"
    origem.mkdir()
    (origem / "chroma.sqlite3").write_bytes(b"isto nao e um sqlite")
    destino = tmp_path / "d"
    with pytest.raises(RuntimeError, match="Nada foi alterado|nao abriu|nao terminou"):
        mig.migrar(cfg, origem=origem, destino=destino, amostra=5, prazo=60, pasta_de_trabalho=tmp_path / "t")
    assert not destino.exists()


def test_com_o_daemon_no_ar_recusa_migrar_o_indice_em_uso(tmp_path, cfg, monkeypatch):
    from delegation_core import daemon
    origem = cfg.chroma_path
    origem.mkdir(parents=True)
    (origem / "chroma.sqlite3").write_bytes(b"x")
    monkeypatch.setattr(daemon, "is_listening", lambda c, *a, **k: True)
    with pytest.raises(RuntimeError, match="daemon esta no ar"):
        mig.migrar(cfg, pasta_de_trabalho=tmp_path / "t")
    # e uma copia explicita nao tem essa trava
    (tmp_path / "copia").mkdir()
    (tmp_path / "copia" / "chroma.sqlite3").write_bytes(b"x")
    monkeypatch.setattr(mig, "exportar_em_filho", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("chegou na exportacao")))
    with pytest.raises(RuntimeError, match="chegou na exportacao"):
        mig.migrar(cfg, origem=tmp_path / "copia", destino=tmp_path / "d", pasta_de_trabalho=tmp_path / "t")


def test_comparar_mede_a_sobreposicao_entre_os_dois_indices(tmp_path, cfg):
    origem = _chroma(tmp_path)
    mig.migrar(cfg, origem=origem, destino=cfg.sqlite_path, amostra=5, pasta_de_trabalho=tmp_path / "t")
    r = mig.comparar(cfg, amostra=10, origem=origem, pasta_de_trabalho=tmp_path / "cmp")
    assert r["colecoes"]["vault_x"]["sobreposicao_media"] >= 0.9


def test_o_estado_padrao_da_migracao_segue_o_redirecionamento_da_suite(tmp_path, cfg, monkeypatch):
    """Sem pasta de trabalho explicita, a exportacao vai para o estado do projeto, que a
    suite redireciona: um teste nunca escreve em ~/.delegation_core de verdade."""
    from delegation_core import config as config_mod
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path / "estado")
    assert mig._pasta_de_estado() == tmp_path / "estado"
