"""Kompress (ModernBERT do Headroom) no roteador: so com modelo em cache, nunca baixa no meio."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from delegation_core.compressao import roteador

HR = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "compressao" / "headroom_py"
ORIGEM = Path.home() / "Projects" / "headroom" / "headroom"

#: Alteracoes locais deliberadas na copia vendorizada, aplicadas ao original antes de comparar.
#: Qualquer outra diferenca continua reprovando o teste. c9ba453 (2026-10-23) estreitou o
#: `except Exception` do import opcional, achado do pyflakes na remediacao.
PATCHES_LOCAIS = {
    "transforms/kompress_compressor.py": [
        ("except Exception:  # pragma: no cover - huggingface_hub always present with [ml]",
         "except (ImportError, ModuleNotFoundError):  # pragma: no cover"),
    ],
}


def _original_com_patches_locais(deles: str, caminho: Path) -> bytes:
    texto = caminho.read_bytes()
    for velho, novo in PATCHES_LOCAIS.get(deles, []):
        assert velho.encode() in texto, f"patch local de {deles} ja nao se aplica ao original: {velho}"
        texto = texto.replace(velho.encode(), novo.encode(), 1)
    return texto


def test_copias_identicas_ao_headroom():
    pares = {"transforms/kompress_compressor.py": "transforms/kompress_compressor.py",
             "transforms/base.py": "transforms/base.py", "onnx_runtime.py": "onnx_runtime.py",
             "transforms/content_detector.py": "transforms/content_detector.py",
             "transforms/lossless_compaction.py": "transforms/lossless_compaction.py",
             "transforms/cross_turn_dedup.py": "transforms/cross_turn_dedup.py",
             "transforms/read_lifecycle.py": "transforms/read_lifecycle.py"}
    if not ORIGEM.exists():
        pytest.skip("copia do Headroom nao esta nesta maquina")
    for nosso, deles in pares.items():
        esperado = _original_com_patches_locais(deles, ORIGEM / deles)
        assert hashlib.sha256((HR / nosso).read_bytes()).digest() == hashlib.sha256(esperado).digest(), nosso


PROSA = (" ".join(["The proxy forwards every request to the provider and compresses tool results before they "
                   "reach the model, which keeps answers the same while the bill shrinks considerably."] * 40))


def test_sem_modelo_o_roteador_segue_sem_kompress(monkeypatch):
    monkeypatch.setattr(roteador, "_kompress", lambda t, g: None)
    r = roteador.comprimir(PROSA, guardar=False)
    assert r["compressor"] != "kompress"


def test_desligado_no_config(monkeypatch):
    from delegation_core import config
    config.Config(kompress_enabled=False).save()
    assert roteador._kompress(PROSA, None) is None


def _modelo_em_cache() -> bool:
    try:
        from delegation_core.compressao.headroom_py.transforms.kompress_compressor import KompressCompressor
        KompressCompressor().preload(allow_download=False)
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _modelo_em_cache(), reason="modelo do Kompress nao esta em cache")
def test_kompress_de_verdade_e_recall():
    import asyncio
    import json
    import delegation_core.server as server
    r = roteador.comprimir(PROSA)
    assert r["compressor"] == "kompress" and r["shown_tokens"] < r["raw_tokens"]
    if r["cache_key"]:
        volta = json.loads(server.recall_output(hash=r["cache_key"]))
        assert volta["output"] == PROSA
