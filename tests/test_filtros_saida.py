"""Porte do motor TOML do RTK: testes embutidos dele, camada de execucao, hook e CLI.

A paridade com o binario real (408 de 420 saidas iguais, hash incluso)
foi medida por `scripts/paridade_rtk.py` em 05/10/2026 e roda aqui quando
RTK_BIN aponta para um binario. As 12 diferentes sao 6 do dotnet-build e 6 do
uv-sync: no RTK esses dois comandos vao para modulos Rust proprios
(dotnet_cmd.rs, uv_cmd.rs), que tem precedencia sobre o filtro TOML.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from delegation_core.filtros_saida import execucao, motor
from delegation_core.filtros_saida.cli import reescrever


def test_os_151_testes_embutidos_do_rtk_passam():
    r = motor.verificar()
    assert r["filters"] == 62 and r["total"] == 151
    assert r["failed"] == [], r["failed"][:3]
    assert r["without_tests"] == []


def _filtro(**kw):
    return motor.compilar("t", {"match_command": "^t\\b", **kw})


def test_estagios_que_os_testes_do_rtk_nao_cobrem():
    """Mutacao mostrou que max_lines, truncate, head, strip_ansi e replace passavam sem teste."""
    assert motor.aplicar(_filtro(max_lines=2), "a\nb\nc\nd") == "a\nb\n... (2 lines truncated)"
    assert motor.aplicar(_filtro(truncate_lines_at=6), "abcdefghij") == "abc..."
    assert motor.aplicar(_filtro(head_lines=1), "a\nb\nc") == "a\n... (2 lines omitted)"
    assert motor.aplicar(_filtro(tail_lines=1), "a\nb\nc") == "... (2 lines omitted)\nc"
    assert motor.aplicar(_filtro(head_lines=1, tail_lines=1), "a\nb\nc\nd") == "a\n... (2 lines omitted)\nd"
    assert motor.aplicar(_filtro(strip_ansi=True), "\x1b[31mvermelho\x1b[0m") == "vermelho"
    assert motor.aplicar(_filtro(replace=[{"pattern": "(\\w+)=(\\d+)", "replacement": "$2:${1}"}]), "x=1") == "1:x"
    assert motor.aplicar(_filtro(on_empty="nada"), "\n\n") == "nada"
    assert motor.aplicar(_filtro(), "a\r\nb\r\n") == "a\nb", "str::lines() do Rust tira o \\r"


def test_recusas_de_compilacao():
    with pytest.raises(motor.ErroDeFiltro, match="mutually exclusive"):
        _filtro(strip_lines_matching=["a"], keep_lines_matching=["b"])
    with pytest.raises(motor.ErroDeFiltro, match="unknown fields"):
        _filtro(cor="azul")
    assert not motor.ancorado("liquibase|^x") and motor.ancorado("(?i)^a|^b")


def test_camada_de_execucao_guarda_e_recupera():
    f = _filtro(max_lines=3)
    bruto = "\n".join(f"linha {i} com algum texto" for i in range(50))
    r = execucao.exibir(f, bruto, "t x")
    assert r["lossy"] and r["recall_hint"].startswith("[+47 hidden: delegation-core recall ")
    h = r["recall_hint"].split()[-1].rstrip("]")
    assert execucao.recuperar(h, 4)["output"].startswith("linha 3 ")
    assert execucao.recuperar(h)["total_lines"] == 50


def test_guarda_nunca_pior_e_falha_guardada():
    f = _filtro(on_empty="t: nenhuma saida relevante neste comando")
    assert execucao.exibir(f, "\n", "t")["output"] == "\n", "o resumo maior que o original perde"
    g = _filtro(strip_lines_matching=["^ok"])
    bruto = "ok\n" * 300 + "erro fatal"
    r = execucao.exibir(g, bruto, "t", codigo=1)
    assert r["output"].startswith("erro fatal\n[full output: delegation-core recall ")


def test_hook_so_reescreve_comando_simples_e_nunca_concede_permissao():
    r = reescrever({"tool_name": "Bash", "tool_input": {"command": "terraform plan -out x", "description": "d"}})
    out = r["hookSpecificOutput"]
    assert out["updatedInput"] == {"command": "delegation-core shell 'terraform plan -out x'", "description": "d"}
    assert "permissionDecision" not in out
    for cmd in ("terraform plan | head", "terraform plan && ls", "terraform plan > f", "echo $(terraform plan)",
                "ls -la", "delegation-core shell 'terraform plan'"):
        assert reescrever({"tool_name": "Bash", "tool_input": {"command": cmd}}) is None, cmd
    assert reescrever({"tool_name": "Read", "tool_input": {"command": "terraform plan"}}) is None


def test_cli_run_de_verdade():
    """Um comando real (df tem filtro), pelo executavel do modulo."""
    p = subprocess.run([sys.executable, "-m", "delegation_core", "shell", "df -h"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and p.stdout.strip()
    p = subprocess.run([sys.executable, "-m", "delegation_core", "shell", "exit 3"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 3, "o codigo de saida e o do comando"


def test_ferramentas_mcp():
    import asyncio
    import delegation_core.server as server
    r = json.loads(asyncio.run(server.filter_output(command="comando-sem-filtro", output="a\nb")))
    assert r == {"output": "a\nb", "filter": None, "lossy": False}
    r = json.loads(asyncio.run(server.filter_output(command="terraform plan",
                                                    output="Refreshing state... [id=1]\n\nPlan: 1 to add")))
    assert r["filter"] == "terraform-plan" and r["output"] == "Plan: 1 to add"
    assert "not_found" in server.recall_output(hash="000000000000")


@pytest.mark.skipif(not os.environ.get("RTK_BIN"), reason="RTK_BIN nao aponta para um binario do RTK")
def test_paridade_com_o_binario_real(tmp_path):
    raiz = Path(__file__).resolve().parents[1]
    p = subprocess.run([sys.executable, str(raiz / "scripts" / "paridade_rtk.py"), str(tmp_path)],
                       capture_output=True, text=True, timeout=900)
    r = json.loads((tmp_path / "resultado.json").read_text())
    diferentes = {d["filtro"] for d in r["diferentes"]}
    assert diferentes <= {"dotnet-build", "uv-sync"}, (diferentes, p.stdout)
