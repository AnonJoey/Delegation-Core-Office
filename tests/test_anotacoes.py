"""Anotacoes MCP: saem da classificacao, e chegam ao cliente pelo protocolo."""

from __future__ import annotations

import asyncio

from delegation_core import anotacoes, escopos


def test_derivadas_da_classificacao():
    assert anotacoes.anotacoes_de("search_vault") == {"readOnlyHint": True, "destructiveHint": False,
                                                      "idempotentHint": True, "openWorldHint": False}
    assert anotacoes.anotacoes_de("vault_forget_note")["destructiveHint"] is True
    assert anotacoes.anotacoes_de("write_note")["readOnlyHint"] is False
    assert anotacoes.anotacoes_de("search_web")["openWorldHint"] is True
    assert anotacoes.anotacoes_de("ferramenta_nova")["readOnlyHint"] is False


def test_o_cliente_recebe_as_anotacoes():
    """Pelo Client do FastMCP sobre o servidor real, nao pelo dicionario."""
    from fastmcp import Client
    import delegation_core.server as server

    async def roda():
        n = await anotacoes.aplicar(server.mcp)
        async with Client(server.mcp) as c:
            return n, {t.name: t.annotations for t in await c.list_tools()}
    n, vistas = asyncio.run(roda())
    assert n == len(vistas) > 90
    assert vistas["read_note"].readOnlyHint is True and vistas["read_note"].destructiveHint is False
    assert vistas["ingest_forget"].destructiveHint is True and vistas["ingest_forget"].readOnlyHint is False
    assert all(vistas[x].readOnlyHint is False for x in escopos.ESCRITA if x in vistas)
