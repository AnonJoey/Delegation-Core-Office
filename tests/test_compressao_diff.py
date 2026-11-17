"""Compressor de diff portado do Headroom. Medicao de 05/10/2026 contra o nucleo
compilado do mesmo codigo: 218 de 218 diffs reais deste repositorio identicos,
com cortes de arquivo, de hunk e marca CCR cobertos."""

from __future__ import annotations

import json
from pathlib import Path

from delegation_core.compressao.diff import DiffCompressor

FIX = Path(__file__).parent / "fixtures" / "headroom"


class _G:
    def __init__(self):
        self.d = {}

    def put(self, k, v):
        self.d[k] = v


def test_casos_do_oraculo():
    casos = json.loads((FIX / "diff_oraculo.json").read_text(encoding="utf-8"))["cases"]
    for c in casos:
        r = DiffCompressor().compress(c["input"], c["context"], store=_G())
        assert r.compressed == c["compressed"], c["context"]
        assert r.hunks_removed == c["hunks_removed"]


def test_curto_ou_sem_diff_passa_direto():
    assert DiffCompressor().compress("a\nb").compressed == "a\nb"
    texto = "\n".join(f"linha {i}" for i in range(80))
    assert DiffCompressor().compress(texto).compressed == texto


def test_marca_ccr_e_guarda():
    linhas = ["diff --git a/x.py b/x.py", "--- a/x.py", "+++ b/x.py", "@@ -1,200 +1,200 @@"]
    linhas += [f" contexto {i}" for i in range(100)] + ["-velho", "+novo"] + [f" contexto {i}" for i in range(100)]
    g = _G()
    r = DiffCompressor().compress("\n".join(linhas), store=g)
    assert r.cache_key in g.d and r.compressed.endswith(f"Retrieve full diff: hash={r.cache_key}]")
    assert "+novo" in r.compressed and " contexto 50" not in r.compressed
