"""Revisoes do config: guarda a anterior, mascara segredo, reverte e o reverter se desfaz."""

from __future__ import annotations

import json
import sys
import stat
from types import SimpleNamespace

import pytest

from delegation_core import config, revisoes_config


def _salva(**kw):
    cfg = config.Config.load()
    for k, v in kw.items():
        setattr(cfg, k, v)
    cfg.save()


def test_guarda_so_quando_muda():
    _salva(server_token="segredo-123")
    assert revisoes_config.listar_arquivos() == [], "o primeiro save nao tem anterior"
    _salva(split_max_notes=3)
    _salva(split_max_notes=3)
    assert len(revisoes_config.listar_arquivos()) == 1


def test_historico_mascara_e_reverte():
    _salva(server_token="segredo-123", default_search_scope="notes")
    _salva(default_search_scope="all", server_token="outro-456")
    revs = revisoes_config.historico()
    assert len(revs) == 1
    mud = {c["key"]: c for c in revs[0]["changes"]}
    assert mud["default_search_scope"] == {"key": "default_search_scope", "before": "notes", "after": "all"}
    assert mud["server_token"]["before"] == "***" and "segredo" not in json.dumps(revs)
    r = revisoes_config.reverter(1)
    assert {c["key"] for c in r["changes"]} == {"default_search_scope", "server_token"}
    assert config.Config.load().default_search_scope == "notes"
    revisoes_config.reverter(1)
    assert config.Config.load().default_search_scope == "all", "reverter tambem se desfaz"


@pytest.mark.skipif(sys.platform == "win32", reason="o Windows nao tem bits de permissao POSIX")
def test_permissao_e_limite(monkeypatch):
    monkeypatch.setattr(config, "REVISOES_MANTER", 3)
    for i in range(6):
        _salva(split_max_notes=i + 1)
    arqs = revisoes_config.listar_arquivos()
    assert len(arqs) == 3
    assert stat.S_IMODE(arqs[0].stat().st_mode) == 0o600


def test_revisao_inexistente():
    import pytest
    with pytest.raises(ValueError):
        revisoes_config.reverter(1)


def test_cli(capsys):
    _salva(split_max_notes=3)
    _salva(split_max_notes=7)
    assert revisoes_config.cmd_config(SimpleNamespace(acao="history", limit=5)) == 0
    assert "3 -> 7" in capsys.readouterr().out
    assert revisoes_config.cmd_config(SimpleNamespace(acao="revert", revision=9)) == 1
    assert revisoes_config.cmd_config(SimpleNamespace(acao="revert", revision=1)) == 0
    assert config.Config.load().split_max_notes == 3


def test_chave_secreta_por_nome_e_sufixo_nao_por_substring():
    s = revisoes_config.chave_secreta
    assert s("server_token") and s("client_tokens") and s("openai_api_key") and s("token")
    assert not s("max_tokens") and not s("tokenizer") and not s("monkey")
    assert revisoes_config.mascarar({"codex": {"token": "x", "scope": "read"}}) == {"codex": {"token": "***", "scope": "read"}}
