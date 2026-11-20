"""Testes para 5.1.16 (arquivo unico dentro de pasta ja registrada) e 5.1.17 (texto repetido por rewind).

Os testes de 5.1.17 usam o chunk_text de verdade: a versao anterior so passava
com ele trocado por um duble, e com o real descartava 0 trechos de uma copia integral.
"""
import pytest

from delegation_core import vault as vault_mod
from delegation_core.config import Config
from delegation_core.ingest import (
    IngestManager,
    _load_registry,
    DeduplicadorDeTexto,
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


import os
import random


def _transcricao(semente: int, falas: int) -> list[str]:
    rnd = random.Random(semente)
    palavras = ["reuniao", "cliente", "horas", "painel", "azure", "relatorio", "semana",
                "entrega", "teste", "ajuste", "prazo", "equipe", "indice", "busca"]
    return [f"Pessoa {rnd.randint(1, 3)}: " + " ".join(rnd.choice(palavras) for _ in range(rnd.randint(8, 30)))
            for _ in range(falas)]


def _linhas_no_indice(vm, caminho) -> int:
    return len(vm.collection.get(where={"path": str(caminho)}, include=["metadatas"])["ids"])


def _texto_no_indice(vm, caminho) -> str:
    return "\n".join(vm.collection.get(where={"path": str(caminho)}, include=["documents"])["documents"])


def _gravar(caminho, linhas, mtime):
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.utime(caminho, (mtime, mtime))


def test_dedup_tira_trecho_repetido_dentro_do_mesmo_arquivo():
    a = _transcricao(1, 40)
    b = _transcricao(2, 10)
    texto = "\n".join(a + b + a[5:30]) + "\n"
    limpo, removidas = DeduplicadorDeTexto().filtrar(texto)
    assert removidas == 25
    assert limpo == "\n".join(a + b) + "\n"


def test_dedup_mantem_frase_curta_que_se_repete_de_verdade():
    texto = "\n".join(["Sim.", "Pessoa 1: vamos ver o painel de horas", "Sim.", "ok", "ok", "Sim."]) + "\n"
    limpo, removidas = DeduplicadorDeTexto().filtrar(texto)
    assert removidas == 0 and limpo == texto


def test_sessao_retomada_nao_reindexa_o_que_a_original_ja_tem(mundo):
    """O caso medido em 28/10: a transcricao retomada repete a original e continua."""
    mgr, vm, fonte = mundo
    original = _transcricao(3, 120)
    continuacao = _transcricao(4, 30)
    _gravar(fonte / "sessao-1.md", original, 1_000_000)
    _gravar(fonte / "sessao-2.md", original + continuacao, 2_000_000)

    r = mgr.ingest(str(fonte))
    assert r["indexed"] == 4  # a.md, b.md e as duas sessoes
    assert r["deduplicated_lines"] == 120
    texto_2 = _texto_no_indice(vm, fonte / "sessao-2.md")
    assert original[0] not in texto_2 and original[-1] not in texto_2
    assert continuacao[0] in texto_2 and continuacao[-1] in texto_2
    assert original[60] in _texto_no_indice(vm, fonte / "sessao-1.md")


def test_copia_integral_nao_vira_linha_e_original_pulado_ainda_conta(mundo):
    mgr, vm, fonte = mundo
    original = _transcricao(5, 80)
    _gravar(fonte / "sessao-1.md", original, 1_000_000)
    assert mgr.ingest(str(fonte))["indexed"] == 3

    # Rodada seguinte: a original nao mudou (pulada), a copia chega agora.
    _gravar(fonte / "sessao-1-rewind.md", original, 2_000_000)
    r = mgr.ingest(str(fonte))
    assert r["skipped_unchanged"] == 3
    assert r["skipped_duplicate"] == 1
    assert _linhas_no_indice(vm, fonte / "sessao-1-rewind.md") == 0

    # E na terceira rodada a copia ja esta carimbada e nao e relida.
    r3 = mgr.ingest(str(fonte))
    assert r3["skipped_unchanged"] == 4 and "skipped_duplicate" not in r3


def test_dedup_desligado_indexa_a_copia(mundo):
    mgr, vm, fonte = mundo
    vm.cfg.ingest_dedup_repeated_text = False
    original = _transcricao(6, 60)
    _gravar(fonte / "sessao-1.md", original, 1_000_000)
    _gravar(fonte / "sessao-2.md", original, 2_000_000)
    r = mgr.ingest(str(fonte))
    assert r["indexed"] == 4 and "deduplicated_lines" not in r
    assert _linhas_no_indice(vm, fonte / "sessao-2.md") > 0


def test_arquivo_que_encolhe_nao_deixa_trecho_velho(mundo):
    mgr, vm, fonte = mundo
    f = fonte / "longo.md"
    f.write_text("\n\n".join(f"paragrafo {i} " + "x" * 400 for i in range(40)), encoding="utf-8")
    mgr.ingest(str(fonte))
    assert _linhas_no_indice(vm, f) > 1
    f.write_text("agora e curto", encoding="utf-8")
    r = mgr.ingest(str(fonte))
    assert _linhas_no_indice(vm, f) == 1
    assert r["stale_chunks_removed"] >= 1
