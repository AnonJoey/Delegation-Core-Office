"""Progresso MCP: chega ao cliente, sem total inventado, e nao aparece no esquema."""

from __future__ import annotations

import asyncio

from delegation_core import progresso


def test_sem_ctx_so_espera():
    async def f():
        return 7
    assert asyncio.run(progresso.com_progresso(None, f(), "x")) == 7


def test_avisos_monotonicos_sem_total():
    avisos = []

    class Ctx:
        async def report_progress(self, progress, total, message):
            avisos.append((progress, total, message))

    async def lento():
        await asyncio.sleep(0.35)
        return "feito"
    assert asyncio.run(progresso.com_progresso(Ctx(), lento(), "relink_folder", intervalo=0.1)) == "feito"
    assert len(avisos) >= 2 and all(t is None for _, t, _ in avisos)
    assert [p for p, _, _ in avisos] == sorted(p for p, _, _ in avisos)
    assert "relink_folder: still running" in avisos[0][2]


def test_erro_do_trabalho_sobe():
    import pytest

    async def quebra():
        raise RuntimeError("x")
    with pytest.raises(RuntimeError):
        asyncio.run(progresso.com_progresso(None, quebra(), "x"))


def test_ctx_nao_vira_parametro_e_o_progresso_chega(monkeypatch):
    """Pelo Client do FastMCP, na ferramenta real, com o trabalho trocado por um lento."""
    from fastmcp import Client
    import delegation_core.server as server

    async def manutencao_lenta():
        await asyncio.sleep(0.3)
        return {"classified": []}
    monkeypatch.setattr(server, "_bg_maintenance_wrapper", manutencao_lenta)
    monkeypatch.setattr(progresso, "INTERVALO", 0.1)
    monkeypatch.setattr(progresso.com_progresso, "__defaults__", (0.1,))
    vistos = []

    async def h(p, t, m):
        vistos.append(p)

    async def roda():
        async with Client(server.mcp) as c:
            esquemas = {t.name: t.inputSchema for t in await c.list_tools()}
            r = await c.call_tool("run_maintenance", {}, progress_handler=h)
            return esquemas, r
    esquemas, r = asyncio.run(roda())
    for nome in ("run_maintenance", "relink_folder", "graph_build", "ingest_folder", "ingest_configured"):
        assert "ctx" not in esquemas[nome].get("properties", {}), nome
    assert vistos, "nenhum aviso de progresso chegou"
