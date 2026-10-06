"""Ferramenta MCP `async` sem nenhum `await` roda no laco de eventos e o trava.

E a classe de defeito do PR 7 (daemon do Mac parado em 26/09/2026). Em 06/10
ainda havia 22 assim, entre elas as `local_task_*`, que liam e regravavam um
JSON de varios MB a cada chamada. Codigo so sincrono vira `def` e o fastmcp o
roda no threadpool; as que gravam configuracao levam `@_serialized`.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "server.py"


def _ferramentas():
    for n in ast.parse(SERVER.read_text(encoding="utf-8")).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                alvo = d.func if isinstance(d, ast.Call) else d
                if isinstance(alvo, ast.Attribute) and alvo.attr == "tool":
                    yield n


def test_nenhuma_ferramenta_async_sem_await():
    ruins = [n.name for n in _ferramentas() if isinstance(n, ast.AsyncFunctionDef)
             and not any(isinstance(x, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for x in ast.walk(n))]
    assert ruins == [], f"async sem await (travam o laco): {ruins}"


def test_as_que_gravam_configuracao_sao_serializadas():
    serializadas = {n.name for n in _ferramentas()
                    if any(isinstance(d, ast.Name) and d.id == "_serialized" for d in n.decorator_list)}
    for nome in ("window_open", "window_close", "workspace_save", "workspace_apply",
                 "graph_hook_install", "graph_hook_uninstall"):
        assert nome in serializadas, nome


def _fastmcp_principal() -> int:
    import fastmcp
    return int(fastmcp.__version__.split(".")[0])


@pytest.mark.skipif(_fastmcp_principal() >= 4, reason=(
    "fastmcp 4 perde o cliente em TODA ferramenta, async ou nao (medido em 06/10/2026 "
    "com o codigo anterior a esta mudanca); o pyproject trava fastmcp<4"))
def test_quem_pediu_a_tarefa_chega_a_thread(tmp_path, monkeypatch):
    """Rodando no threadpool, a tarefa ainda sabe qual cliente a enviou."""
    from fastmcp import Client
    from mcp.types import Implementation

    import delegation_core.server as server
    from delegation_core import localqueue
    monkeypatch.setattr(localqueue, "STORE_PATH", tmp_path / "t.json")

    async def chamar():
        async with Client(server.mcp, client_info=Implementation(name="cliente-de-teste", version="1")) as c:
            return await c.call_tool("local_task_submit", {"prompt": "oi"})
    r = json.loads(asyncio.run(chamar()).content[0].text)
    assert r["submitted_by"] == "cliente-de-teste"
