from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from delegation_core import clientes_extra


@pytest.fixture
def casa(tmp_path, monkeypatch):
    monkeypatch.setattr(clientes_extra.Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


CFG = SimpleNamespace(server_url="http://127.0.0.1:8787/mcp", server_token="TOK")


def test_cursor_preserva_outros_servidores_e_faz_copia(casa):
    arq = casa / ".cursor" / "mcp.json"
    arq.parent.mkdir()
    arq.write_text(json.dumps({"mcpServers": {"outro": {"command": "x"}}}))
    assert clientes_extra.install_cursor(CFG)["status"] == "installed"
    d = json.loads(arq.read_text())
    assert d["mcpServers"]["outro"] == {"command": "x"}
    assert d["mcpServers"]["delegation-core"]["headers"]["Authorization"] == "Bearer TOK"
    assert arq.with_suffix(".json.dc-backup").exists()
    assert clientes_extra.install_cursor(CFG)["status"] == "already-configured"


def test_opencode_formato_remoto(casa):
    assert clientes_extra.install_opencode(CFG)["status"] == "installed"
    d = json.loads((casa / ".config" / "opencode" / "opencode.json").read_text())
    assert d["mcp"]["delegation-core"] == {"type": "remote", "url": CFG.server_url, "enabled": True,
                                           "headers": {"Authorization": "Bearer TOK"}}


def test_json_quebrado_nao_e_sobrescrito(casa):
    arq = casa / ".cursor" / "mcp.json"
    arq.parent.mkdir()
    arq.write_text("{ quebrado")
    assert clientes_extra.install_cursor(CFG)["status"] == "error"
    assert arq.read_text() == "{ quebrado"
