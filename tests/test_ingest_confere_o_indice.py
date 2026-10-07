"""A ingestao nao pode confiar so no carimbo do registro.

O carimbo (mtime e tamanho) diz que o ARQUIVO nao mudou. Quem diz se o INDICE tem as
linhas dele e o indice. Com o indice recriado, esvaziado ou trocado, pular so pelo
carimbo devolvia "0 files" sem reembutir nada.
"""
import pytest

from delegation_core import vault as vault_mod
from delegation_core.config import Config
from delegation_core.ingest import IngestManager
from delegation_core.vault import VaultManager

from tests.test_indice_sqlite_vault import _Embedder


@pytest.fixture
def mundo(monkeypatch, tmp_path):
    import delegation_core.config as config_mod
    import delegation_core.ingest as ingest_mod
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ingest_mod, "_REGISTRY_FILE", tmp_path / "ingested_sources.json")
    monkeypatch.setattr(vault_mod, "make_bge_embedding_function", lambda *a, **k: _Embedder())
    cfg = Config(vault_path=str(tmp_path / "vault"), index_backend="sqlite", embed_device="cpu")
    (tmp_path / "vault").mkdir()
    fonte = tmp_path / "docs"
    fonte.mkdir()
    (fonte / "a.md").write_text("Primeiro documento sobre bolsao e semaforo.", encoding="utf-8")
    (fonte / "b.md").write_text("Segundo documento sobre o indice sqlite.", encoding="utf-8")
    vm = VaultManager(cfg)
    vm._init()
    return IngestManager(vm), vm, fonte


def _linhas_da_fonte(vm, fonte):
    return len(vm.collection.get(where={"source_folder": str(fonte)}, include=[])["ids"])


def test_indice_intacto_pula_o_que_nao_mudou(mundo):
    mgr, vm, fonte = mundo
    assert mgr.ingest(str(fonte))["indexed"] == 2
    r = mgr.ingest(str(fonte))
    assert r["indexed"] == 0 and r["skipped_unchanged"] == 2 and r["reindexed_missing_from_index"] == 0


def test_indice_esvaziado_reembute_em_vez_de_dizer_zero(mundo):
    mgr, vm, fonte = mundo
    mgr.ingest(str(fonte))
    vm.collection.delete(where={"source_folder": str(fonte)})
    assert _linhas_da_fonte(vm, fonte) == 0
    r = mgr.ingest(str(fonte))
    assert r["indexed"] == 2, "pulou pelo carimbo com o indice vazio"
    assert r["reindexed_missing_from_index"] == 2 and r["skipped_unchanged"] == 0
    assert _linhas_da_fonte(vm, fonte) == 2


def test_so_o_arquivo_que_sumiu_do_indice_e_reembutido(mundo):
    mgr, vm, fonte = mundo
    mgr.ingest(str(fonte))
    vm.collection.delete(where={"path": str(fonte / "a.md")})
    r = mgr.ingest(str(fonte))
    assert r["indexed"] == 1 and r["skipped_unchanged"] == 1 and r["reindexed_missing_from_index"] == 1


def test_outra_fonte_com_o_mesmo_nome_de_arquivo_nao_conta_como_presente(mundo, tmp_path):
    mgr, vm, fonte = mundo
    outra = tmp_path / "docs2"
    outra.mkdir()
    (outra / "a.md").write_text("Primeiro documento sobre bolsao e semaforo.", encoding="utf-8")
    mgr.ingest(str(fonte))
    mgr.ingest(str(outra))
    vm.collection.delete(where={"source_folder": str(outra)})
    r = mgr.ingest(str(outra))
    assert r["indexed"] == 1, "as linhas de OUTRA fonte nao podem fazer esta parecer presente"


def test_se_o_indice_nao_puder_ser_consultado_vale_o_carimbo(mundo, monkeypatch):
    mgr, vm, fonte = mundo
    mgr.ingest(str(fonte))
    monkeypatch.setattr(vm.collection.__class__, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("indice fora")))
    r = mgr.ingest(str(fonte))
    assert r["skipped_unchanged"] == 2 and r["indexed"] == 0


def test_force_nao_consulta_o_indice(mundo):
    mgr, vm, fonte = mundo
    mgr.ingest(str(fonte))
    r = mgr.ingest(str(fonte), force=True)
    assert r["indexed"] == 2 and r["reindexed_missing_from_index"] == 0
