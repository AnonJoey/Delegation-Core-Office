"""O fim do wizard: daemon registrado e clientes ligados, sem blocos stdio.

Medido em 06/10/2026 num HOME limpo: depois de um wizard completo nao existia
unit do daemon, nem ~/.claude.json, e a tela final mandava colar
`"args": ["run"]`, que faz cada cliente subir o proprio daemon.
Nada aqui chama systemctl nem escreve nos arquivos reais: `service` e
`clients` sao substituidos e o HOME aponta para tmp_path.
"""
from __future__ import annotations

import pytest

from delegation_core import clients, service, wizard
from delegation_core.config import Config


@pytest.fixture
def casa(tmp_path, monkeypatch):
    monkeypatch.setattr(wizard.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(wizard.shutil, "which", lambda n: None)
    monkeypatch.setattr(clients, "claude_desktop_config_path",
                        lambda: tmp_path / "Claude" / "claude_desktop_config.json")
    monkeypatch.setattr(clients, "ANTIGRAVITY_CONFIG", tmp_path / ".gemini" / "config" / "mcp.json")
    return tmp_path


@pytest.fixture
def chamadas(monkeypatch):
    feitas: list[str] = []
    monkeypatch.setattr(service, "install", lambda: feitas.append("service.install") or {"status": "installed"})
    monkeypatch.setattr(service, "restart", lambda: feitas.append("service.restart") or {"status": "restarted"})
    monkeypatch.setattr(service, "is_up", lambda wait_seconds=0.0: False if not wait_seconds else True)
    for nome in ("claude_code", "claude_desktop", "codex", "antigravity"):
        monkeypatch.setattr(clients, f"install_{nome}",
                            lambda cfg, _n=nome: feitas.append(_n) or {"status": "installed"})
    monkeypatch.setattr(clients, "register_session_hooks",
                        lambda *a, **k: feitas.append("hooks") or {"status": "installed"})
    monkeypatch.setattr(wizard, "_setup_startup", lambda cfg: feitas.append("llama_unit"))
    return feitas


def _respostas(monkeypatch, *itens):
    fila = list(itens)
    monkeypatch.setattr(wizard.console, "input", lambda *a, **k: fila.pop(0) if fila else "")


def test_registra_o_daemon_e_liga_so_os_clientes_que_existem(casa, chamadas, monkeypatch):
    (casa / ".claude").mkdir()
    (casa / "Claude").mkdir()
    _respostas(monkeypatch, "")
    r = wizard._step_connect(Config(vault_path=str(casa / "v")), auto_start=True)
    assert chamadas == ["service.install", "llama_unit", "claude_code", "hooks", "claude_desktop"]
    assert r["daemon"] == "running"
    assert set(r["clients"]) == {"claude_code", "claude_desktop"}


def test_sem_auto_start_nao_registra_servico_mas_liga_clientes(casa, chamadas, monkeypatch):
    (casa / ".codex").mkdir()
    _respostas(monkeypatch, "")
    r = wizard._step_connect(Config(vault_path=str(casa / "v")), auto_start=False)
    assert "service.install" not in chamadas and "llama_unit" not in chamadas
    assert chamadas == ["codex"]
    assert r["daemon"] == "not_registered"


def test_recusar_nao_escreve_em_nenhum_cliente(casa, chamadas, monkeypatch):
    (casa / ".claude").mkdir()
    _respostas(monkeypatch, "n")
    r = wizard._step_connect(Config(vault_path=str(casa / "v")), auto_start=False)
    assert chamadas == [] and r["clients"] == {}


def test_daemon_ja_no_ar_pergunta_e_reinicia(casa, chamadas, monkeypatch):
    monkeypatch.setattr(service, "is_up", lambda wait_seconds=0.0: True)
    _respostas(monkeypatch, "y")
    wizard._step_connect(Config(vault_path=str(casa / "v")), auto_start=True)
    assert "service.restart" in chamadas


def test_falha_do_servico_nao_derruba_o_wizard(casa, chamadas, monkeypatch):
    def quebra():
        raise OSError("sem systemd")
    monkeypatch.setattr(service, "install", quebra)
    r = wizard._step_connect(Config(vault_path=str(casa / "v")), auto_start=True)
    assert r["daemon"] == "registration_failed"


def test_falha_de_um_cliente_nao_impede_os_outros(casa, chamadas, monkeypatch):
    (casa / ".claude").mkdir()
    (casa / ".codex").mkdir()
    def quebra(cfg):
        raise PermissionError("negado")
    monkeypatch.setattr(clients, "install_claude_code", quebra)
    _respostas(monkeypatch, "")
    r = wizard._step_connect(Config(vault_path=str(casa / "v")), auto_start=False)
    assert r["clients"]["claude_code"] == "error"
    assert r["clients"]["codex"] == "installed"


def test_mlx_nunca_ganha_a_unit_do_llama(casa, monkeypatch):
    registradas = []
    for nome in ("_startup_systemd", "_startup_launchd", "_startup_task_scheduler"):
        monkeypatch.setattr(wizard, nome, lambda cfg, _n=nome: registradas.append(_n))
    cfg = Config(vault_path=str(casa / "v"), engine_mode="local")
    cfg.llama_binary = "/opt/mlx_lm.server"
    cfg.llama_model = "mlx-community/Qwen3-0.6B-4bit"
    cfg.motor_local = "mlx"
    wizard._setup_startup(cfg)
    assert registradas == []
    cfg.motor_local = "llamacpp"
    wizard._setup_startup(cfg)
    assert len(registradas) == 1


def test_a_tela_final_nao_imprime_o_bloco_stdio_que_duplica_o_daemon(capsys):
    wizard.console.record = False
    with wizard.console.capture() as cap:
        wizard._completion(Config(vault_path="/v"), {"daemon": "running", "clients": {"claude_code": "installed"}})
    texto = cap.get()
    assert '"run"' not in texto and "mcpServers" not in texto
    assert "delegation-core clients" not in texto or "Connected" in texto
    assert "Claude Code" in texto and "/mcp" in texto


def test_a_tela_final_diz_quando_nada_foi_ligado():
    with wizard.console.capture() as cap:
        wizard._completion(Config(vault_path="/v"), {})
    assert "delegation-core clients" in cap.get()


def test_enter_aceita_a_recomendacao_so_quando_ha_padrao(monkeypatch):
    _respostas(monkeypatch, "")
    assert wizard._menu_index("Choose", 2, padrao=1) == 1
    _respostas(monkeypatch, "", "2")
    assert wizard._menu_index("Choose", 2) == 1  # sem padrao, Enter e recusado


def test_o_token_existe_antes_de_qualquer_cliente_ser_escrito(casa, chamadas, monkeypatch):
    (casa / ".claude").mkdir()
    vistos = []
    monkeypatch.setattr(clients, "install_claude_code",
                        lambda cfg: vistos.append(cfg.server_token) or {"status": "installed"})
    _respostas(monkeypatch, "")
    cfg = Config(vault_path=str(casa / "v"))
    assert cfg.server_token == ""
    wizard._step_connect(cfg, auto_start=False)
    assert vistos and vistos[0] and vistos[0] == cfg.server_token
