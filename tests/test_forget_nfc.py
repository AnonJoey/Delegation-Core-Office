"""forget precisa achar o caminho em qualquer forma Unicode (NFC ou NFD).

Medido em 21/11/2026 num Mac: a pasta gravada em NFD no indice e o pedido
em NFC; `ingest_forget` respondia `removed_chunks: 0` sem erro.
"""
import json
import unicodedata as u

import pytest

import delegation_core.ingest as ing
from delegation_core.indice_sqlite import ClienteSqlite


class Vault:
    def __init__(self, colecao):
        self.collection = colecao

    def _ensure_ready(self):
        pass


def gerente(colecao):
    m = ing.IngestManager.__new__(ing.IngestManager)
    m._vault = Vault(colecao)
    return m


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(ing, "_REGISTRY_FILE", tmp_path / "registro.json")
    cliente = ClienteSqlite(tmp_path / "indice")
    colecao = cliente.get_or_create_collection("teste")
    yield tmp_path, colecao
    cliente.close()


def gravar(colecao, linhas):
    colecao.upsert(
        ids=[i for i, _, _ in linhas],
        embeddings=[[1.0, 0.0] for _ in linhas],
        documents=[f"texto {i}" for i, _, _ in linhas],
        metadatas=[{"is_external": "true", "path": p, "source_folder": s} for _, p, s in linhas],
    )


@pytest.mark.parametrize("pedido,gravado", [("NFC", "NFD"), ("NFD", "NFC"), ("NFC", "NFC"), ("NFD", "NFD")])
def test_forget_ignora_a_forma_unicode(ambiente, pedido, gravado):
    tmp, colecao = ambiente
    raiz = str(tmp.resolve() / "Capacitação")
    f = lambda s, forma=gravado: u.normalize(forma, s)
    gravar(colecao, [
        ("dentro", f(raiz + "/Reuniões/a.pdf"), f(str(tmp.resolve()))),
        ("fundo", f(raiz + "/x/y/b.pdf"), f(str(tmp.resolve()))),
        ("vizinha", f(raiz + " Antiga/c.pdf"), f(str(tmp.resolve()))),
        ("prefixo", f(raiz + "2/d.pdf"), f(str(tmp.resolve()))),
    ])
    ing._REGISTRY_FILE.write_text(json.dumps({f(raiz): {"files": 2}, "/outra": {"files": 1}}), encoding="utf-8")

    r = gerente(colecao).forget(u.normalize(pedido, raiz))

    assert r["removed_chunks"] == 2
    assert r["registry_entry_removed"] is True
    assert set(colecao.get()["ids"]) == {"vizinha", "prefixo"}
    assert set(json.loads(ing._REGISTRY_FILE.read_text(encoding="utf-8"))) == {"/outra"}


def test_forget_por_source_folder_acentuada(ambiente):
    tmp, colecao = ambiente
    raiz = str(tmp.resolve() / "Relatórios")
    gravar(colecao, [("a", "", u.normalize("NFD", raiz)), ("b", "/fora/b.pdf", "/fora")])
    r = gerente(colecao).forget(u.normalize("NFC", raiz))
    assert r["removed_chunks"] == 1
    assert colecao.get()["ids"] == ["b"]


def test_grafia_exata_vence_a_outra_forma(ambiente):
    """No Linux os dois nomes podem existir lado a lado: o pedido por um nao leva o outro."""
    tmp, colecao = ambiente
    raiz = str(tmp.resolve() / "Capacitação")
    nfc, nfd = u.normalize("NFC", raiz), u.normalize("NFD", raiz)
    gravar(colecao, [("nfc", nfc + "/a.pdf", ""), ("nfd", nfd + "/a.pdf", "")])
    ing._REGISTRY_FILE.write_text(json.dumps({nfc: {"files": 1}, nfd: {"files": 1}}), encoding="utf-8")

    r = gerente(colecao).forget(nfc)

    assert r["removed_chunks"] == 1
    assert colecao.get()["ids"] == ["nfd"]
    assert set(json.loads(ing._REGISTRY_FILE.read_text(encoding="utf-8"))) == {nfd}
