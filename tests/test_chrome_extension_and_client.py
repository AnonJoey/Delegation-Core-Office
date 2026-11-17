"""Tests for the Chrome MCP client registration helpers.

The extension itself is not shipped here: it belongs to @frankorozcogt/mcp-chrome-server.
"""

import json
from pathlib import Path

from delegation_core import clients
from delegation_core.windows import SELF




def test_chrome_mcp_entry_structure():
    """Verify chrome_mcp_entry returns a valid stdio MCP config dict."""
    entry = clients.chrome_mcp_entry()
    assert isinstance(entry, dict)
    assert "command" in entry
    assert isinstance(entry.get("args"), list)


def test_install_chrome_antigravity(tmp_path):
    """Test installing chrome MCP entry into an Antigravity config file."""
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps({
        "mcpServers": {
            "delegation-core": {"serverUrl": "http://127.0.0.1:8787/mcp"}
        }
    }), encoding="utf-8")

    result = clients.install_chrome_antigravity(target_path=config_file)
    assert result["status"] == "installed"

    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert "chrome" in data["mcpServers"]
    assert "delegation-core" in data["mcpServers"]

    # Idempotence
    result_again = clients.install_chrome_antigravity(target_path=config_file)
    assert result_again["status"] == "already-configured"


def test_install_chrome_claude_code(monkeypatch, tmp_path):
    """Test installing chrome MCP entry into ~/.claude.json."""
    import delegation_core.windows as windows_mod
    client_config = tmp_path / "claude.json"
    client_config.write_text(json.dumps({
        "mcpServers": {
            SELF: {"type": "http", "url": "http://127.0.0.1:8787/mcp"}
        }
    }), encoding="utf-8")
    monkeypatch.setattr(windows_mod, "CLIENT_CONFIG", client_config)

    result = clients.install_chrome_claude_code()
    assert result["status"] == "installed"

    data = json.loads(client_config.read_text(encoding="utf-8"))
    assert "chrome" in data["mcpServers"]
    assert SELF in data["mcpServers"]
