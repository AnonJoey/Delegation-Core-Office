"""O VaultManager inteiro sobre o indice SQLite, comparado com o mesmo sobre o Chroma.

Embedder falso e deterministico (palavras em dimensoes fixas): notas que dividem
palavras ficam proximas, o que da busca de verdade sem baixar o BGE.
"""
import hashlib
import re

import numpy as np
import pytest

from delegation_core import vault as vault_mod
from delegation_core.config import Config
from delegation_core.vault import VaultManager

DIM = 64


class _Embedder:
    def __call__(self, input):
        out = []
        for texto in input:
            v = np.zeros(DIM, dtype=np.float32)
            for w in re.findall(r"\w+", texto.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
            n = np.linalg.norm(v)
            out.append((v / n if n else v).tolist())
        return out

    def embed_documents(self, input):
        return self(input)

    def embed_query(self, input):
        return self([input])[0] if isinstance(input, str) else self(list(input))

    def name(self):
        return "falso"


NOTAS = {
    "Decisions/vigia-de-bolsao.md": "---\ntitle: Vigia de bolsao\n---\nO bolsao do Angelus estourou em outubro.",
    "Decisions/semaforo.md": "---\ntitle: Semaforo\n---\nO semaforo de cores do painel segue a regua do RF-02.",
    "Fixes/chromadb.md": "---\ntitle: Corrupcao\n---\nO ChromaDB corrompe o indice quando dois processos escrevem.",
    "Reference/daily.md": "---\ntitle: Daily\n---\nA daily da equipe dev comeca as quatorze horas.",
}


def _vault(tmp_path, monkeypatch, backend, nome):
    raiz = tmp_path / nome
    for rel, texto in NOTAS.items():
        p = raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    cfg = Config(vault_path=str(raiz), vault_folders=["Decisions", "Fixes", "Reference"],
                 index_backend=backend, embed_device="cpu")
    monkeypatch.setattr(vault_mod, "make_bge_embedding_function", lambda *a, **k: _Embedder())
    return VaultManager(cfg)


@pytest.fixture
def ambos(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    return (_vault(tmp_path, monkeypatch, "chroma", "c"),
            _vault(tmp_path, monkeypatch, "sqlite", "s"))


def _titulos(r):
    return [x["title"] for x in (r["sources"] if isinstance(r, dict) else r)]


def test_indexar_e_buscar_da_as_mesmas_notas_nos_dois_backends(ambos):
    for vm in ambos:
        vm.reindex_vault(force=True)
    for pergunta in ("bolsao do Angelus", "semaforo cores", "corrompe indice", "daily quatorze", "zzz"):
        a, b = (vm.search(pergunta, limit=3) for vm in ambos)
        assert _titulos(a) == _titulos(b), pergunta


def test_escrever_apagar_e_estatisticas(ambos):
    for vm in ambos:
        vm.reindex_vault(force=True)
        vm.index_note("O servidor do Claude falha na troca de modelo.",
                      {"title": "Troca de modelo", "path": "Fixes/troca.md", "folder": "Fixes"})
    a, b = (vm.search("troca de modelo", limit=2) for vm in ambos)
    assert _titulos(a) == _titulos(b) and "Troca de modelo" in _titulos(b)
    for vm in ambos:
        vm.delete_notes(["Fixes/troca.md"])
    a, b = (vm.search("troca de modelo", limit=5) for vm in ambos)
    assert "Troca de modelo" not in _titulos(b)
    sa, sb = (vm.get_stats() for vm in ambos)
    assert sa["indexed_rows"] == sb["indexed_rows"]
    assert sa["indexed_notes"] == sb["indexed_notes"]


def test_outro_processo_escreve_e_o_primeiro_ve_sem_reabrir(tmp_path, monkeypatch):
    """O que o _reload_if_disk_changed do Chroma precisava reabrir o cliente para ver."""
    vm1 = _vault(tmp_path, monkeypatch, "sqlite", "s")
    vm1.reindex_vault(force=True)
    antes = len(_titulos(vm1.search("nota nova do outro processo", limit=10)))
    vm2 = VaultManager(vm1.cfg)            # outro cliente sobre o mesmo arquivo
    vm2.index_note("Texto sobre a nota nova do outro processo.",
                   {"title": "Nota nova", "path": "Decisions/nova.md", "folder": "Decisions"})
    depois = _titulos(vm1.search("nota nova do outro processo", limit=10))
    assert "Nota nova" in depois and len(depois) >= antes


def test_sem_chromadb_aberto_o_backend_sqlite_nao_cria_pasta_do_chroma(tmp_path, monkeypatch):
    vm = _vault(tmp_path, monkeypatch, "sqlite", "s")
    vm.reindex_vault(force=True)
    raiz = tmp_path / "s"
    assert not (raiz / ".chroma_bge").exists()
    assert (raiz / ".indice_sqlite" / "indice.db").exists()
