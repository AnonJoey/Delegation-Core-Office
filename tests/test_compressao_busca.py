"""Compressor de busca portado do Headroom. Medicao de 05/10/2026 contra o
nucleo compilado do mesmo codigo: 160 de 160 saidas reais de rg/grep
identicas (155 com corte, 151 com marca CCR), mais caminhos de Windows e
nomes de arquivo com `-`, as duas correcoes do Rust sobre o Python."""

from __future__ import annotations

import json
from pathlib import Path

from delegation_core.compressao.busca import SearchCompressor, parse_match_line
from delegation_core.compressao.sinais import categoria

FIX = Path(__file__).parent / "fixtures" / "headroom"


class _G:
    def put(self, k, v):
        pass


def test_casos_do_oraculo():
    for c in json.loads((FIX / "busca_oraculo.json").read_text(encoding="utf-8"))["cases"]:
        r = SearchCompressor().compress(c["input"], c["context"], c["bias"], store=_G())
        assert r.compressed == c["compressed"], c["name"]
        assert r.compressed_match_count == c["count"]


def test_leitura_das_linhas():
    assert parse_match_line("src/a.py:42:def f():") == ("src/a.py", 42, "def f():")
    assert parse_match_line("C:\\x\\a.py:7:y") == ("C:\\x\\a.py", 7, "y")
    assert parse_match_line("pre-commit-config.yaml-42-  - id: x") == ("pre-commit-config.yaml", 42, "  - id: x")
    assert parse_match_line("sem marca nenhuma") is None


def test_sinais():
    assert categoria("Connection timeout after 3s") == "error"
    assert categoria("input_tokens = 5") is None, "token nao e seguranca (correcao do Rust)"
    assert categoria("WARNING: x") == "warning" and categoria("# Titulo", "text") == "markdown"
