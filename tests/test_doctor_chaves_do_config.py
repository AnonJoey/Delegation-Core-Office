"""O doctor avisa de chave do config.json que o Config nao conhece.

`Config.load` descarta em silencio toda chave que nao e campo (config.py:764).
No servidor gss o config.json tinha `llama_parallel` e nenhum campo com esse
nome: a opcao era ignorada e nada, em lugar nenhum, avisava. Erro de digitacao
tem o mesmo efeito: `llama_ctxx = 8192` parece valer e nao vale.
"""
from __future__ import annotations

import json

from delegation_core import doctor


def _config(tmp_path, dados):
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return caminho


def test_config_so_com_chaves_conhecidas_esta_ok(tmp_path):
    r = doctor.check_config_keys(_config(tmp_path, {"engine_mode": "agent", "llama_ctx": 4096}))
    assert r["status"] == "ok"


def test_chave_desconhecida_vira_aviso_com_o_nome(tmp_path):
    r = doctor.check_config_keys(_config(tmp_path, {"engine_mode": "agent", "llama_ctxx": 8192}))
    assert r["status"] == "warn"
    assert "llama_ctxx" in r["detail"]
    assert "fix" in r


def test_sugere_o_campo_parecido(tmp_path):
    r = doctor.check_config_keys(_config(tmp_path, {"llama_ctxx": 8192}))
    assert "llama_ctx" in r["detail"].replace("llama_ctxx", "")


def test_sem_arquivo_nao_e_aviso(tmp_path):
    r = doctor.check_config_keys(tmp_path / "nao-existe.json")
    assert r["status"] == "ok"


def test_arquivo_ilegivel_e_aviso(tmp_path):
    caminho = tmp_path / "config.json"
    caminho.write_text("{ nao e json", encoding="utf-8")
    r = doctor.check_config_keys(caminho)
    assert r["status"] == "warn"


def test_roda_dentro_do_run_all(monkeypatch, tmp_path):
    """Ter a funcao nao basta: o doctor precisa chamá-la."""
    import inspect
    assert "check_config_keys" in inspect.getsource(doctor.run_all)
