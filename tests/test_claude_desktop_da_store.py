"""Claude Desktop da Microsoft Store le a configuracao de dentro do pacote MSIX.

Medido em 23/11/2026 num Windows com o Claude instalado pela Store
(`AppData/Local/Packages/Claude_pzs8sxrjxfjjc`): `clients --claude-desktop`
respondia `already-configured` sobre `AppData/Roaming/Claude`, e o Desktop,
reiniciado, carregava os outros servidores MCP e nao o delegation-core. A
entrada estava num arquivo que o app nao le. Gravada no arquivo que o proprio
Desktop abre em Configuracoes > Desenvolvedor, a ponte subiu e respondeu.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from delegation_core import clients


@pytest.fixture
def windows(tmp_path, monkeypatch):
    monkeypatch.setattr(clients.platform, "system", lambda: "Windows")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _roaming(home: Path) -> Path:
    return home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"


def test_sem_pacote_da_store_fica_o_roaming(windows):
    assert clients.claude_desktop_config_path() == _roaming(windows)


def test_com_pacote_da_store_vai_para_o_localcache(windows):
    pasta = windows / "AppData" / "Local" / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude"
    pasta.mkdir(parents=True)
    assert clients.claude_desktop_config_path() == pasta / "claude_desktop_config.json"


def test_pacote_que_nunca_rodou_nao_desvia(windows):
    """Sem LocalCache o app ainda nao tem copia redirecionada: o Roaming vale."""
    (windows / "AppData" / "Local" / "Packages" / "Claude_pzs8sxrjxfjjc").mkdir(parents=True)
    assert clients.claude_desktop_config_path() == _roaming(windows)


def test_outro_pacote_com_prefixo_parecido_nao_conta(windows):
    pasta = windows / "AppData" / "Local" / "Packages" / "ClaudeHelper.Algo_xyz" / "LocalCache" / "Roaming" / "Claude"
    pasta.mkdir(parents=True)
    assert clients.claude_desktop_config_path() == _roaming(windows)


def test_install_grava_no_arquivo_que_a_store_le(windows):
    from delegation_core.config import Config
    pasta = windows / "AppData" / "Local" / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude"
    pasta.mkdir(parents=True)
    r = clients.install_claude_desktop(Config(vault_path="/tmp/vault", server_token="tok", server_port=8797))
    assert Path(r["path"]) == pasta / "claude_desktop_config.json"
    assert (pasta / "claude_desktop_config.json").is_file()
    assert not _roaming(windows).exists()
