from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from delegation_core import clientes_extra, clients, registro_clientes


@pytest.fixture
def casa(tmp_path, monkeypatch):
    monkeypatch.setattr(registro_clientes.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(clients, "CODEX_CONFIG", tmp_path / ".codex" / "config.toml")
    monkeypatch.setattr(clients, "ANTIGRAVITY_CONFIG", tmp_path / ".gemini" / "mcp_config.json")
    monkeypatch.setattr(clients, "claude_desktop_config_path", lambda: tmp_path / "desktop.json")
    monkeypatch.setattr(clients, "claude_desktop_entry", lambda cfg: {"command": "dc", "args": ["mcp-stdio"]})
    return tmp_path


CFG = SimpleNamespace(server_url="http://127.0.0.1:8787/mcp", server_token="TOK")


def _por(itens):
    return {i["client"]: i for i in itens}


def test_estados(casa):
    (casa / ".claude.json").write_text(json.dumps({"mcpServers": {"delegation-core": clients.claude_code_entry(CFG)}}))
    velho = dict(clients.claude_code_entry(CFG), headers={"Authorization": "Bearer ANTIGO"})
    (casa / "desktop.json").write_text(json.dumps({"mcpServers": {"outro": {}}}))
    (casa / ".codex").mkdir()
    (casa / ".codex" / "config.toml").write_text(clients.codex_block(CFG).replace("8787", "9999"))
    (casa / ".gemini").mkdir()
    (casa / ".gemini" / "mcp_config.json").write_text("{ quebrado")
    clientes_extra.install_cursor(CFG)
    r = _por(registro_clientes.estado(CFG))
    assert r["claude-code"]["status"] == "aligned"
    assert r["claude-desktop"]["status"] == "missing" and r["claude-desktop"]["fix"].endswith("--claude-desktop")
    assert r["codex"]["status"] == "stale" and "url" in r["codex"]["detail"]
    assert r["antigravity"]["status"] == "invalid"
    assert r["cursor"]["status"] == "aligned"
    assert r["opencode"]["status"] == "not_installed"

    (casa / ".claude.json").write_text(json.dumps({"mcpServers": {"delegation-core": velho}}))
    assert _por(registro_clientes.estado(CFG))["claude-code"]["detail"] == "differs in: headers"


def test_check_do_doctor(casa):
    c = registro_clientes.check(CFG)
    assert c["status"] == "ok" and "no MCP client" in c["detail"]
    (casa / ".claude.json").write_text("nao e json")
    c = registro_clientes.check(CFG)
    assert c["status"] == "warn" and "claude-code=invalid" in c["detail"]


def test_doctor_nao_escreve(casa):
    (casa / ".claude.json").write_text(json.dumps({"mcpServers": {}}))
    antes = sorted(p.name for p in casa.rglob("*"))
    registro_clientes.check(CFG)
    assert sorted(p.name for p in casa.rglob("*")) == antes
