"""Motor local MLX (mlx_lm.server) no lugar do llama.cpp, para os Macs.

Medido em 06/10/2026 contra o mlx_lm.server 0.32 de verdade, com
mlx-community/Qwen3-0.6B-4bit:
- `"model": "local"`, que o engine mandava fixo, falha em TODA chamada: o
  servidor trata o nome como um repositorio a carregar. `"default_model"` usa o
  modelo que ele subiu com --model.
- `/health` responde 200 e `chat_template_kwargs.enable_thinking=false` e aceito.
- Com o servidor fora, o engine tentava subir o llama-server com --ctx-size e -fa,
  que o mlx_lm.server recusa.
Os testes abaixo seguem esses fatos; o dublê de Popen nao aceita nada que o
servidor real recuse.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from delegation_core import doctor
from delegation_core.config import Config
from delegation_core.engine import DelegationEngine


def _cfg(tmp_path, **kw):
    binario = tmp_path / "mlx_lm.server"
    binario.write_text("")
    base = dict(motor_local="mlx", llama_binary=str(binario), llama_model="mlx-community/Qwen3.8-27B-8bit",
                engine_mode="local", vault_path=str(tmp_path), llama_port=8181)
    base.update(kw)
    return Config(**base)


def test_nome_do_modelo_no_pedido():
    assert Config().modelo_no_pedido == "local"
    assert Config(motor_local="mlx").modelo_no_pedido == "default_model"
    assert Config(motor_local=" MLX ").motor_e_mlx


def test_o_pedido_leva_o_nome_que_o_mlx_entende(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    eng = DelegationEngine(cfg)
    enviados = []

    class Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                                "usage": {"completion_tokens": 1}}

    async def post(url, json=None, **k):
        enviados.append(json)
        return Resp()

    async def saude(force=False):
        return True
    monkeypatch.setattr(eng, "check_health", saude)
    monkeypatch.setattr(eng._async_client, "post", post)
    try:
        r = asyncio.run(eng.invoke("p", max_tokens=5, task="default", force_local=True))
    finally:
        asyncio.run(eng.aclose())
    assert r == "ok"
    assert enviados[0]["model"] == "default_model"
    assert enviados[0]["chat_template_kwargs"] == {"enable_thinking": False}


class _Popen:
    vistos: list = []

    def __init__(self, cmd, **k):
        # O mlx_lm.server recusa as flags do llama.cpp; o dublê tambem.
        for proibida in ("--ctx-size", "-fa", "-ctk", "-ctv", "--n-gpu-layers"):
            assert proibida not in cmd, f"flag do llama.cpp no mlx_lm.server: {proibida}"
        _Popen.vistos.append(cmd)

    def poll(self):
        return None

    def terminate(self): pass
    def wait(self, timeout=None): return 0
    def kill(self): pass


def test_sobe_o_mlx_com_os_argumentos_dele(tmp_path, monkeypatch):
    import delegation_core.engine as engine_mod
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(type(cfg), "llama_log_path", property(lambda self: tmp_path / "llama.log"))
    eng = DelegationEngine(cfg)
    _Popen.vistos = []
    monkeypatch.setattr(engine_mod.subprocess, "Popen", _Popen)
    monkeypatch.setattr(engine_mod.time, "sleep", lambda s: None)
    saude = iter([False, True])
    monkeypatch.setattr(eng, "_is_healthy", lambda: next(saude))
    try:
        assert eng._start() is True
    finally:
        asyncio.run(eng.aclose())
    cmd = _Popen.vistos[0]
    assert cmd[1:3] == ["--model", "mlx-community/Qwen3.8-27B-8bit"]
    assert cmd[cmd.index("--port") + 1] == "8181" and cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--chat-template-args") + 1] == '{"enable_thinking": false}'
    assert eng._we_started_it


def test_modelo_mlx_inexistente_nao_sobe(tmp_path, monkeypatch):
    import delegation_core.engine as engine_mod
    cfg = _cfg(tmp_path, llama_model=str(tmp_path / "nao" / "existe"))
    eng = DelegationEngine(cfg)
    monkeypatch.setattr(engine_mod.subprocess, "Popen", lambda *a, **k: pytest.fail("nao devia subir"))
    try:
        assert eng._start() is False
    finally:
        asyncio.run(eng.aclose())


def test_llamacpp_continua_com_as_flags_de_sempre(tmp_path, monkeypatch):
    import delegation_core.engine as engine_mod
    modelo = tmp_path / "m.gguf"
    modelo.write_text("")
    cfg = _cfg(tmp_path, motor_local="llamacpp", llama_model=str(modelo))
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
    assert "--ctx-size" in vistos[0] and "-fa" in vistos[0]


def test_doctor_aceita_id_do_hugging_face_so_no_mlx(tmp_path):
    assert doctor.check_engine_mode(_cfg(tmp_path))["status"] == "ok"
    assert doctor.check_engine_mode(_cfg(tmp_path, motor_local="llamacpp"))["status"] == "error"
