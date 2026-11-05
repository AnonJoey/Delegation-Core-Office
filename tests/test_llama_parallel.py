"""`llama_parallel`: quantos pedidos o llama-server atende ao mesmo tempo.

O campo existia so numa edicao sem commit no checkout antigo do Office do
servidor gss, e o config.json de la ja trazia `llama_parallel = 1`. O Config
descarta em silencio qualquer chave que nao e campo, entao a configuracao
estava sendo ignorada. Aqui o campo vira de verdade.
"""
from __future__ import annotations

import asyncio

import delegation_core.engine as engine_mod
from delegation_core.config import Config
from delegation_core.engine import DelegationEngine


def _comando_de_subida(tmp_path, monkeypatch, **kw):
    modelo = tmp_path / "m.gguf"
    modelo.write_text("")
    binario = tmp_path / "llama-server"
    binario.write_text("")
    cfg = Config(vault_path=str(tmp_path), llama_binary=str(binario), llama_model=str(modelo),
                 motor_local="llamacpp", **kw)
    monkeypatch.setattr(type(cfg), "llama_log_path", property(lambda self: tmp_path / "llama.log"))
    eng = DelegationEngine(cfg)
    vistos = []

    class P:
        def __init__(self, cmd, **k): vistos.append(cmd)
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): return 0
        def kill(self): pass
    monkeypatch.setattr(engine_mod.subprocess, "Popen", P)
    monkeypatch.setattr(engine_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(engine_mod.gpu, "take", lambda who: 0)
    monkeypatch.setattr(eng, "_is_healthy", lambda: True)
    try:
        assert eng._start() is True
    finally:
        asyncio.run(eng.aclose())
    return vistos[0]


def test_padrao_e_um_e_nao_manda_a_flag(tmp_path, monkeypatch):
    assert Config().llama_parallel == 1
    cmd = _comando_de_subida(tmp_path, monkeypatch)
    assert "--parallel" not in cmd


def test_mais_de_um_vira_flag_parallel(tmp_path, monkeypatch):
    cmd = _comando_de_subida(tmp_path, monkeypatch, llama_parallel=3)
    assert cmd[cmd.index("--parallel") + 1] == "3"


def test_zero_ou_negativo_nao_manda_a_flag(tmp_path, monkeypatch):
    assert "--parallel" not in _comando_de_subida(tmp_path, monkeypatch, llama_parallel=0)
