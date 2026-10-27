"""A ingestao dizia "indexado" para o arquivo cuja gravacao no indice falhou.

Achado em 26/10/2026 num ensaio da migracao para o indice SQLite: o daemon recusou os
dois arquivos (`IndiceSqliteErro: ... dimension of 1024, got 768`, `index_note: ... was NOT
indexed`) e a CLI respondeu "2 files indexed, 0 skipped, 0 errors". `ingest.py` descartava
o retorno de `index_note`, entao o arquivo entrava em `indexed` e era carimbado no
registro. Agora a gravacao que falha vira erro, o arquivo nao e carimbado e a proxima
ingestao tenta de novo.
"""
import pytest

from tests.test_ingest_confere_o_indice import mundo  # noqa: F401  (fixture)


def test_gravacao_que_falha_vira_erro_e_nao_conta_como_indexada(mundo):
    mgr, vm, fonte = mundo
    vm.index_note = lambda *a, **k: False
    r = mgr.ingest(str(fonte))
    assert r["indexed"] == 0
    assert len(r["errors"]) == 2
    assert all("not indexed" in e for e in r["errors"])


def test_arquivo_cuja_gravacao_falhou_nao_e_carimbado_e_entra_na_proxima(mundo):
    mgr, vm, fonte = mundo
    original = vm.index_note
    vm.index_note = lambda *a, **k: False
    mgr.ingest(str(fonte))
    vm.index_note = original
    r = mgr.ingest(str(fonte))
    assert r["indexed"] == 2 and r["skipped_unchanged"] == 0 and not r["errors"]
