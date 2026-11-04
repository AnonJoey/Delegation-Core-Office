"""O reindex incremental nao reembute nota cujo texto ja esta no indice.

Medido em 04/11/2026 no servidor gss: 41.685 das 81.478 notas do vault tinham
data de modificacao de 28 a 29/10 (um relink em massa regravou os arquivos),
e o servidor acusava 44.349 notas "mudadas". O reindex decidia so pela data,
entao reembutiria todas. O BGE-m3 na CPU do servidor faz 1,18 trechos por
segundo (48 trechos de 3000 caracteres em 40,7 s), ou seja, mais de dez horas
de trabalho para texto que nao mudou.

A regra nova: se a data difere, compara o texto que o indice teria gravado com
o que ele ja tem. Igual: so carimba a data nova. Diferente, ausente ou com
sobra de trecho: reembute como antes.
"""
from __future__ import annotations

import hashlib
import os
import re

import numpy as np
import pytest

from delegation_core import vault as vault_mod
from delegation_core.config import Config
from delegation_core.vault import VaultManager

DIM = 64


class _Embedder:
    """Embedder falso que conta quantos textos recebeu."""

    chamadas = 0

    def __call__(self, input):
        out = []
        for texto in input:
            type(self).chamadas += 1
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


NOTA = "---\ntitle: Vigia\n---\nO bolsao do Angelus estourou em outubro."


@pytest.fixture
def vm(tmp_path, monkeypatch):
    _Embedder.chamadas = 0
    raiz = tmp_path / "v"
    (raiz / "Decisions").mkdir(parents=True)
    (raiz / "Decisions" / "vigia.md").write_text(NOTA, encoding="utf-8")
    cfg = Config(vault_path=str(raiz), vault_folders=["Decisions"],
                 index_backend="sqlite", embed_device="cpu")
    monkeypatch.setattr(vault_mod, "make_bge_embedding_function", lambda *a, **k: _Embedder())
    v = VaultManager(cfg)
    v.reindex_vault(force=True)
    _Embedder.chamadas = 0
    return v


def _arquivo(vm):
    return vm.cfg.vault / "Decisions" / "vigia.md"


def _toca(vm, segundos=3600):
    """Muda so a data, como o relink em massa fez."""
    st = _arquivo(vm).stat()
    os.utime(_arquivo(vm), (st.st_atime, st.st_mtime + segundos))


def test_data_nova_com_texto_igual_nao_reembute(vm):
    _toca(vm)

    feitos = vm.reindex_vault()

    assert feitos == 0
    assert _Embedder.chamadas == 0


def test_data_nova_com_texto_igual_carimba_a_data_nova(vm):
    _toca(vm)
    vm.reindex_vault()

    estado = vm._load_index_state()

    assert estado["Decisions/vigia.md"] == pytest.approx(_arquivo(vm).stat().st_mtime)
    # E o segundo reindex pula pela data, sem nem comparar texto.
    assert vm.reindex_vault() == 0


def test_texto_diferente_reembute_e_fica_buscavel(vm):
    _arquivo(vm).write_text(NOTA + " Revisado com aumento de teto.", encoding="utf-8")
    _toca(vm)

    feitos = vm.reindex_vault()

    assert feitos == 1
    assert _Embedder.chamadas >= 1
    achados = vm.search("aumento de teto", limit=3)
    achados = achados["sources"] if isinstance(achados, dict) else achados
    assert any("Vigia" == x["title"] for x in achados)


def test_nota_sem_linhas_no_indice_e_reindexada_mesmo_com_texto_igual(vm):
    vm.collection.delete(where={"path": "Decisions/vigia.md"})
    _toca(vm)

    feitos = vm.reindex_vault()

    assert feitos == 1
    assert _Embedder.chamadas >= 1


def test_sobra_de_trecho_no_indice_forca_reindexar(vm):
    """Trecho a mais que o texto atual nao produz: texto velho respondendo busca."""
    vm.collection.upsert(
        ids=["Decisions/vigia.md::chunk_7"], documents=["trecho velho"],
        metadatas=[{"path": "Decisions/vigia.md", "chunk": "7", "total_chunks": "9"}],
    )
    _toca(vm)

    feitos = vm.reindex_vault()

    assert feitos == 1
    assert "Decisions/vigia.md::chunk_7" not in (vm.collection.get(
        where={"path": "Decisions/vigia.md"}).get("ids") or [])


def test_force_continua_reembutindo_tudo(vm):
    feitos = vm.reindex_vault(force=True)

    assert feitos == 1
    assert _Embedder.chamadas >= 1
