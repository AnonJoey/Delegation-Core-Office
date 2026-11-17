"""Roteador: detecta e manda para o compressor certo; os modulos do Headroom vieram sem mudanca."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import delegation_core.server as server
from delegation_core.compressao import roteador

HR = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "compressao" / "headroom_py" / "transforms"


def test_diff_real_deste_repositorio():
    raiz = Path(__file__).resolve().parents[1]
    d = subprocess.run(["git", "-C", str(raiz), "log", "-p", "-n", "3", "--format=", "--", "src/delegation_core/escopos.py"],
                       capture_output=True, text=True).stdout
    if len(d.split("\n")) < 60:
        return
    r = roteador.comprimir(d, "escopos")
    assert r["content_type"] == "diff" and r["shown_tokens"] <= r["raw_tokens"]


def test_busca_log_e_texto():
    busca = "\n".join(f"src/m{i % 9}.py:{i}:    value_{i} = compute({i})" for i in range(300))
    r = roteador.comprimir(busca, "compute")
    assert r["content_type"] == "search" and r["compressor"] == "search" and r["cache_key"]
    log = "\n".join([f"INFO step {i} ok" for i in range(500)] + ["ERROR disk full"])
    r = roteador.comprimir(log)
    assert r["compressor"] == "log" and "ERROR disk full" in r["output"]
    curto = "nada para comprimir"
    assert roteador.comprimir(curto)["output"] == curto


def test_nunca_maior_que_o_original_e_tipo_invalido():
    import pytest
    for t in ("x", "a\n" * 3, "{}"):
        r = roteador.comprimir(t)
        assert r["shown_tokens"] <= r["raw_tokens"]
    with pytest.raises(ValueError):
        roteador.comprimir("x", tipo="yaml")


def test_ferramenta_e_recall():
    busca = "\n".join(f"lib/a{i % 4}.rs:{i}:fn item_{i}() {{}}" for i in range(400))
    r = json.loads(asyncio.run(server.compress_output(content=busca)))
    volta = json.loads(server.recall_output(hash=r["cache_key"]))
    assert volta["output"] == busca
    assert "invalid_input" in asyncio.run(server.compress_output(content="x", kind="yaml"))


def test_modulos_do_headroom_sem_modificacao():
    """Copiados do Headroom; o sha256 confere com a copia baixada quando ela existe."""
    import hashlib
    origem = Path.home() / "Projects" / "headroom" / "headroom" / "transforms"
    for nome in ("content_detector.py", "lossless_compaction.py"):
        if (origem / nome).exists():
            assert hashlib.sha256((HR / nome).read_bytes()).digest() == hashlib.sha256((origem / nome).read_bytes()).digest()
