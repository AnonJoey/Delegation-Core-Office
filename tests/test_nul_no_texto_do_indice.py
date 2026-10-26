"""Um NUL no meio do texto de um documento corrompia o FTS5 do ChromaDB.

Diagnostico de 26/10/2026 (maquina do Saad): o indice de busca textual voltou a corromper
entre 15:33 e 15:39, depois da reingestao de PDFs, com o doctor dando "healthy" as 15:33 e
`--rebuild-fts` tendo consertado as 13:56. Reproduzido aqui sem concorrencia, com o
chromadb 1.5.9: um documento com NUL no meio deixa o `integrity-check` em "database disk
image is malformed" ja no `add`; NUL no fim nao faz mal; `rebuild` conserta e um `upsert`
sem o NUL tambem. 1 de 396 PDFs desta maquina extrai texto com NUL.
"""
import sqlite3

import pytest

from delegation_core.config import Config
from delegation_core.doctor import check_fts_integrity, documentos_com_nul
from delegation_core.embeddings import texto_indexavel
from delegation_core.vault import VaultManager

chromadb = pytest.importorskip("chromadb")

NUL = chr(0)


def _vetores(n):
    return [[0.1 * (i + 1), 0.2, 0.3, 0.4] for i in range(n)]


def _indice_chroma(pasta, documentos):
    cliente = chromadb.PersistentClient(path=str(pasta))
    col = cliente.get_or_create_collection("tst")
    col.add(ids=[f"x{i}" for i in range(len(documentos))], documents=documentos,
            embeddings=_vetores(len(documentos)))
    del col, cliente


def _integridade(pasta):
    con = sqlite3.connect(str(pasta / "chroma.sqlite3"))
    try:
        con.execute("INSERT INTO embedding_fulltext_search(embedding_fulltext_search) "
                    "VALUES('integrity-check')")
        con.commit()
        return "ok"
    except sqlite3.DatabaseError as e:
        return str(e)
    finally:
        con.close()


class ColecaoFalsa:
    def __init__(self):
        self.documentos = []

    def delete(self, **_k):
        pass

    def upsert(self, ids, documents, metadatas):
        self.documentos.extend(documents)


def test_texto_indexavel_troca_o_nul_por_espaco_e_tira_o_substituto():
    assert texto_indexavel("abc" + NUL + "def") == "abc def"
    assert texto_indexavel("a\ud800b" + NUL + "c") == "ab c"
    assert texto_indexavel("coração, 東京") == "coração, 東京"
    assert texto_indexavel("") == ""


def _pular_se_nao_corrompe(pasta):
    """Cria o indice com NUL e pula o teste se esta combinacao de chromadb e sqlite nao
    corrompe: na CI do Ubuntu (python 3.12, chromadb 1.5.9) o defeito nao apareceu, no
    macOS, no Windows e no Linux com python 3.14 e sqlite 3.54 sim. O conserto vale nos
    dois casos; so o teste do defeito depende do ambiente."""
    _indice_chroma(pasta, ["abc" + NUL + "def ghi jkl", "outro documento qualquer"])
    if "malformed" not in _integridade(pasta):
        pytest.skip(f"o NUL nao corrompe aqui (sqlite {sqlite3.sqlite_version}, "
                    f"chromadb {chromadb.__version__})")


def test_o_defeito_existe_no_chroma_sem_o_conserto(tmp_path):
    """O experimento que justifica o conserto: se o chromadb deixar de corromper, este
    teste pula e o conserto pode ser reavaliado."""
    _pular_se_nao_corrompe(tmp_path)
    assert "malformed" in _integridade(tmp_path)


def test_o_texto_limpo_nao_corrompe_o_chroma(tmp_path):
    docs = [texto_indexavel(d) for d in ["abc" + NUL + "def ghi jkl", NUL + "inicio", "fim" + NUL]]
    _indice_chroma(tmp_path, docs)
    assert _integridade(tmp_path) == "ok"


def test_index_note_grava_o_texto_de_um_pdf_com_nul(tmp_path):
    v = VaultManager(Config(vault_path=str(tmp_path)))
    v._ensure_ready = lambda: None
    v.collection = ColecaoFalsa()
    v._read_disk_state = lambda: None
    assert v.index_note("glifo" + NUL + "sem mapa", {"path": "Reference/pdf.md", "kind": "note"}) is True
    assert v.collection.documentos == ["glifo sem mapa"]


def test_doctor_diz_a_causa_quando_o_indice_esta_corrompido_por_nul(tmp_path):
    _pular_se_nao_corrompe(tmp_path)
    cfg = Config(vault_path=str(tmp_path / "vault"), index_path=str(tmp_path))
    cfg.index_backend = "chroma"
    r = check_fts_integrity(cfg)
    assert r["status"] == "error"
    assert "1 stored document(s) contain a NUL" in r["detail"]
    assert documentos_com_nul(tmp_path / "chroma.sqlite3") == 1


def test_doctor_avisa_do_nul_mesmo_com_o_indice_saudavel(tmp_path):
    _indice_chroma(tmp_path, ["abc" + NUL + "def ghi jkl", "outro"])
    con = sqlite3.connect(str(tmp_path / "chroma.sqlite3"))
    con.execute("INSERT INTO embedding_fulltext_search(embedding_fulltext_search) VALUES('rebuild')")
    con.commit()
    con.close()
    cfg = Config(vault_path=str(tmp_path / "vault"), index_path=str(tmp_path))
    cfg.index_backend = "chroma"
    r = check_fts_integrity(cfg)
    assert r["status"] == "warn" and "NUL" in r["detail"]


def test_doctor_segue_ok_sem_nul(tmp_path):
    _indice_chroma(tmp_path, ["texto normal", "outro texto"])
    cfg = Config(vault_path=str(tmp_path / "vault"), index_path=str(tmp_path))
    cfg.index_backend = "chroma"
    r = check_fts_integrity(cfg)
    assert r["status"] == "ok"
