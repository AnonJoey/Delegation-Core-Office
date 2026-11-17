"""Registro anotado dos modulos Rust do RTK e o desvio do filter_output para os compressores."""

from __future__ import annotations

import asyncio
import json

import delegation_core.server as server
from delegation_core.filtros_saida import modulos_rtk


def test_registro_completo():
    r = modulos_rtk.resumo()
    assert r["modules"] == 69 and r["code_lines"] > 30000
    assert all(m["description"] for m in modulos_rtk.registro())


def test_registro_e_portados_concordam():
    """rtk_modulos.json marca `ported` ou `partial` exatamente os modulos em modulos.PORTADOS.

    `partial`: git e gh, de que so alguns subcomandos foram portados (`ported_subcommands`)."""
    import importlib

    from delegation_core.filtros_saida import modulos
    marcados = {m["module"]: m.get("python_module") for m in modulos_rtk.registro()
                if m["status"] in ("ported", "partial")}
    assert set(marcados) == set(modulos.PORTADOS)
    assert modulos_rtk.resumo()["ported"] == len(modulos.PORTADOS)
    for rtk, py in modulos.PORTADOS.items():
        assert marcados[rtk] == f"delegation_core.filtros_saida.modulos.{py}"
        assert callable(importlib.import_module(marcados[rtk]).filtrar)
    parciais = {m["module"] for m in modulos_rtk.registro() if m["status"] == "partial"}
    assert parciais == set(modulos.PARCIAIS)
    for m in modulos_rtk.registro():
        assert bool(m.get("ported_subcommands")) == (m["status"] == "partial")


def test_comando_para_modulo():
    assert modulos_rtk.modulo_para("git log --oneline")["module"] == "git/git_cmd"
    assert modulos_rtk.modulo_para("pytest -x tests/")["module"] == "python/pytest_cmd"
    assert modulos_rtk.modulo_para("/usr/bin/cargo test")["module"] == "rust/cargo_cmd"
    assert modulos_rtk.modulo_para("php artisan migrate")["module"] == "php/artisan_cmd"
    assert modulos_rtk.modulo_para("comando-inventado") is None


def test_filter_output_desvia_para_o_compressor():
    # cargo: modulo anotado e ainda nao portado (o pytest, que servia de exemplo, foi portado).
    log = "\n".join([f"test tests::caso_{i} ... ok" for i in range(300)] + ["test tests::caso_z ... FAILED", "error: test failed, to rerun pass `--lib`"])
    r = json.loads(asyncio.run(server.filter_output(command="cargo test", output=log)))
    assert r["rtk_module"] == "rust/cargo_cmd" and r["compressor"] == "log"
    assert "caso_z" in r["output"] and r["shown_tokens"] < r["raw_tokens"]
