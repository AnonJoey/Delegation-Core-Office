"""Testes para 5.1.16 (arquivo unico dentro de pasta ja registrada) e 5.1.17 (rewind/dedup de chunks)."""
import pytest

from delegation_core import vault as vault_mod
from delegation_core.config import Config
from delegation_core.ingest import (
    IngestManager,
    _load_registry,
    deduplicar_blocos_repetidos,
)
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
    fonte = tmp_path / "knowledge"
    fonte.mkdir()
    (fonte / "a.md").write_text("Primeiro documento da pasta knowledge.", encoding="utf-8")
    (fonte / "b.md").write_text("Segundo documento da pasta knowledge.", encoding="utf-8")
    vm = VaultManager(cfg)
    vm._init()
    return IngestManager(vm), vm, fonte


def test_arquivo_unico_dentro_de_pasta_registrada_nao_cria_segunda_fonte(mundo):
    mgr, vm, fonte = mundo
    assert mgr.ingest(str(fonte))["indexed"] == 2
    assert len(_load_registry()) == 1

    # Reingerir um arquivo avulso com --force nao pode criar uma fonte nova nem apagar o outro arquivo do registro
    alvo = fonte / "a.md"
    r = mgr.ingest(str(alvo), force=True)
    assert r["indexed"] == 1
    assert r["source"] == str(fonte)
    assert r["reused_parent_source"] == str(fonte)

    reg = _load_registry()
    assert list(reg.keys()) == [str(fonte)]
    assert str(alvo) in reg[str(fonte)]["files"]
    assert str(fonte / "b.md") in reg[str(fonte)]["files"]

    # Os metadados no indice mantiveram source_folder da pasta pai
    metas = vm.collection.get(where={"path": str(alvo)}, include=["metadatas"])["metadatas"]
    assert metas and all(m["source_folder"] == str(fonte) for m in metas)

    # Rodar a pasta pai de novo sem --force pula ambos sem reindexar nada
    r2 = mgr.ingest(str(fonte))
    assert r2["indexed"] == 0 and r2["skipped_unchanged"] == 2


def test_arquivo_unico_fora_de_pasta_registrada_cria_fonte_propria(mundo, tmp_path):
    mgr, _vm, fonte = mundo
    mgr.ingest(str(fonte))
    avulso = tmp_path / "avulso.md"
    avulso.write_text("Documento fora da pasta registrada.", encoding="utf-8")

    r = mgr.ingest(str(avulso))
    assert r["indexed"] == 1
    assert r["source"] == str(avulso)
    assert "reused_parent_source" not in r
    assert set(_load_registry().keys()) == {str(fonte), str(avulso)}


def test_deduplicar_blocos_repetidos_remove_rewind_e_preserva_curtos():
    bloco_longo = (
        "Transcricao da reuniao semanal de alinhamento tecnico sobre a migracao do indice "
        "SQLite e a validacao das rotinas de ingestao externa no servidor."
    )
    bloco_unico = (
        "Outro trecho completamente distinto falando sobre o cronograma de entregas da fase dois "
        "e os criterios de homologacao dos relatorios semanais."
    )
    curto = "--- pausa ---"
    chunks = [bloco_longo, curto, "  " + bloco_longo.upper() + "  ", curto, bloco_unico]
    unicos, descartados = deduplicar_blocos_repetidos(chunks)
    assert descartados == 1
    assert unicos == [bloco_longo, curto, curto, bloco_unico]


def test_ingest_transcricao_com_rewind_descarta_chunks_duplicados(mundo, monkeypatch):
    mgr, vm, fonte = mundo
    bloco = (
        "Trecho longo de transcricao gravado pelo app que acabou repetido identicamente "
        "por causa de um rewind na captura de audio durante a reuniao."
    )
    bloco_fim = (
        "Conclusao da reuniao com as acoes definidas para a proxima sprint e confirmacao "
        "dos responsaveis por cada entregavel tecnico."
    )
    transcricao = fonte / "reuniao.md"
    transcricao.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "delegation_core.ingest.chunk_text",
        lambda content, max_chars, overlap: [bloco, bloco, bloco_fim] if content == "placeholder" else [content],
    )
    r = mgr.ingest(str(transcricao), force=True)
    assert r["indexed"] == 1
    assert r["deduplicated_chunks"] == 1

    rows = vm.collection.get(where={"path": str(transcricao)}, include=["metadatas"])
    assert len(rows["ids"]) == 2
    assert all(m["total_chunks"] == "2" for m in rows["metadatas"])
