"""Um caractere substituto solto no texto de um PDF deixava o arquivo inteiro fora da busca.

Diagnostico de 26/10/2026: tres erros `index_note ... TypeError: TextEncodeInput must be
Union[...]` num PDF. O tokenizador nao aceita U+D800 a U+DFFF e a mensagem nao diz isso;
reproduzido com `"a\\ud800b"`. O texto passa a ser limpo antes de ser dividido e embutido.
"""
from delegation_core.config import Config
from delegation_core.embeddings import sem_surrogatos
from delegation_core.vault import VaultManager


class ColecaoFalsa:
    def __init__(self):
        self.documentos = []

    def delete(self, **_k):
        pass

    def upsert(self, ids, documents, metadatas):
        # O mesmo teste que o tokenizador faz: texto com substituto solto nao serializa.
        for d in documents:
            d.encode("utf-8")
        self.documentos.extend(documents)


def test_sem_surrogatos_tira_so_o_caractere_quebrado():
    assert sem_surrogatos("a\ud800b\udfffc") == "abc"
    assert sem_surrogatos("coração, 東京, ok") == "coração, 東京, ok"
    assert sem_surrogatos("") == ""


def test_index_note_grava_o_texto_de_um_pdf_com_substituto_solto(tmp_path):
    v = VaultManager(Config(vault_path=str(tmp_path)))
    v._ensure_ready = lambda: None
    v.collection = ColecaoFalsa()
    v._read_disk_state = lambda: None
    assert v.index_note("texto \ud83d quebrado", {"path": "Reference/pdf.md", "kind": "note"}) is True
    assert v.collection.documentos == ["texto  quebrado"]
