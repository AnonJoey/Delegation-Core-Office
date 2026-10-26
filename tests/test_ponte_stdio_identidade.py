"""A ponte stdio se identifica ao daemon (diagnostico de 26/10/2026: toda conexao aparecia como "mcp 0.1.0")."""
import sys
import types

from delegation_core import __version__, stdio_bridge
from delegation_core.config import Config


def test_cliente_da_ponte_leva_nome_e_versao_do_delegation_core(monkeypatch):
    chamadas = []
    fastmcp = types.ModuleType("fastmcp")
    fastmcp.Client = lambda transporte, **kw: chamadas.append(kw) or "cliente"
    transportes = types.ModuleType("fastmcp.client.transports")
    transportes.StreamableHttpTransport = lambda **kw: "transporte"
    monkeypatch.setitem(sys.modules, "fastmcp", fastmcp)
    monkeypatch.setitem(sys.modules, "fastmcp.client.transports", transportes)

    assert stdio_bridge.cliente_da_ponte(Config(server_token="t")) == "cliente"

    info = chamadas[0]["client_info"]
    assert info.name == "delegation-core-stdio-bridge" and info.version == __version__
