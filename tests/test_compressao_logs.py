"""Compressor de logs portado do Headroom: casos do oraculo e as gravacoes de paridade.

O oraculo e o `headroom._core` compilado a partir do mesmo codigo do porte
(`scripts/paridade_headroom.py`). Medicao de 05/10/2026: 1006 de 1029 iguais
(3 vieses sobre 343 logs, reais e sinteticos); os 23 restantes diferem so no
numero de linhas mantidas, porque o Rust valida o corte comprimindo com
miniz_oxide e o porte com a zlib, e as duas dao tamanhos diferentes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from delegation_core.compressao import adaptativo
from delegation_core.compressao.ccr import Guarda
from delegation_core.compressao.logs import LogCompressor, classify, flavor_for, normalize_for_dedupe

FIX = Path(__file__).parent / "fixtures" / "headroom"


class _G:
    def __init__(self):
        self.d = {}

    def put(self, k, v):
        self.d[k] = v


def test_casos_do_oraculo():
    casos = json.loads((FIX / "log_oraculo.json").read_text())["cases"]
    iguais = 0
    for c in casos:
        r = LogCompressor().compress(c["input"], c["bias"], store=_G())
        assert r.format_detected == c["format"]
        iguais += r.compressed == c["compressed"]
    assert iguais >= len(casos) - 2, f"{iguais}/{len(casos)}"


@pytest.mark.parametrize("arq", sorted((FIX / "parity_log").glob("*.json")), ids=lambda p: p.stem)
def test_gravacoes_de_paridade_do_headroom(arq):
    d = json.loads(arq.read_text())
    cfg = d["config"]
    from delegation_core.compressao.logs import LogCompressorConfig
    conf = LogCompressorConfig(**{k: v for k, v in cfg.items() if k in LogCompressorConfig.__dataclass_fields__})
    entrada = d["input"]["content"] if isinstance(d["input"], dict) else d["input"]
    bias = d["input"].get("bias", 1.0) if isinstance(d["input"], dict) else 1.0
    r = LogCompressor(conf).compress(entrada, bias, store=_G())
    esperado = d["output"]
    assert r.compressed_line_count == esperado["compressed_line_count"]
    assert r.format_detected == esperado["format_detected"]


def test_detalhes():
    assert classify("2026 WARNING disk") == "warn" and classify("errors=0") == "unknown"
    assert classify("ERROR: x") == "error" and classify("warningly") == "unknown"
    assert flavor_for("Traceback (most recent call last):") == "python"
    assert flavor_for("   at Acme.Svc.Run() in /src/Svc.cs:line 33") == "dotnet"
    assert flavor_for("goroutine 1 [running]:") == "go"
    assert normalize_for_dedupe("segfault at 0x7f: addr 0x1f") != normalize_for_dedupe("heap overflow at 0x7f: addr 0x1f")
    assert adaptativo.compute_optimal_k(["a"] * 5) == 5


def test_guarda_reversivel_e_recall():
    import asyncio
    import delegation_core.server as server
    linhas = [f"INFO step {i} ok" for i in range(400)] + ["ERROR disk full at /data"]
    r = LogCompressor().compress("\n".join(linhas), 1.0, store=Guarda())
    assert r.cache_key and r.compressed.endswith(f"Retrieve more: hash={r.cache_key}]")
    volta = json.loads(server.recall_output(hash=r.cache_key))
    assert volta["output"] == "\n".join(linhas) and volta["total_lines"] == 401
