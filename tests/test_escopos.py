"""Escopo por cliente: classificacao completa, verificacao de token, middleware e CLI."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from delegation_core import escopos
from delegation_core.auth import LocalTokenAuth

SERVER = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "server.py"


def _ferramentas():
    texto = SERVER.read_text(encoding="utf-8")
    # Outros decoradores (@_serialized) podem vir entre @mcp.tool() e o def.
    return set(re.findall(r"^@mcp\.tool\(\)\s*\n(?:@\w+\s*\n)*(?:async )?def (\w+)", texto, re.M))


def test_toda_ferramenta_esta_classificada_e_so_uma_vez():
    """Nega por padrao so funciona se ninguem esquecer de classificar."""
    todas = _ferramentas()
    assert len(todas) > 50
    assert not (escopos.LEITURA & escopos.ESCRITA)
    assert todas - (escopos.LEITURA | escopos.ESCRITA) == set(), "ferramenta nova sem escopo"
    assert (escopos.LEITURA | escopos.ESCRITA) - todas == set(), "classificacao de ferramenta que nao existe"


@pytest.mark.parametrize("ferr,escopo,ok", [
    ("search_vault", ["read"], True), ("write_note", ["read"], False), ("write_note", ["read", "write"], True),
    ("ferramenta_nova_sem_classe", ["read"], False), ("vault_note_restore", ["read"], False),
    ("write_note", None, True), ("write_note", ["master"], True),
])
def test_permitido(ferr, escopo, ok):
    assert escopos.permitido(ferr, escopo) is ok


def _auth(nomeados):
    return LocalTokenAuth("MESTRE-" + "x" * 30, tokens_nomeados=lambda: nomeados)


def test_verificacao_de_token():
    a = _auth({"codex": {"token": "LEITURA-" + "a" * 30, "scope": "read"},
               "desktop": {"token": "ESCRITA-" + "b" * 30, "scope": "write"}})
    v = lambda t: asyncio.run(a.verify_token(t))  # noqa: E731
    assert v("MESTRE-" + "x" * 30).scopes == ["master"]
    r = v("LEITURA-" + "a" * 30)
    assert r.scopes == ["read"] and r.client_id == "client:codex"
    assert v("ESCRITA-" + "b" * 30).scopes == ["read", "write"]
    assert v("errado") is None and v("") is None


def test_config_ilegivel_deixa_so_o_mestre():
    def quebra():
        raise ValueError("json quebrado")
    a = LocalTokenAuth("M" * 30, tokens_nomeados=quebra)
    assert asyncio.run(a.verify_token("M" * 30)).scopes == ["master"]
    assert asyncio.run(a.verify_token("qualquer")) is None


def test_ler_tokens_rele_quando_o_arquivo_muda(tmp_path):
    import os
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"client_tokens": {"a": {"token": "t1", "scope": "read"}}}))
    assert list(escopos.ler_tokens(p)) == ["a"]
    p.write_text(json.dumps({"client_tokens": {}}))
    os.utime(p, ns=(p.stat().st_mtime_ns + 10**9,) * 2)
    assert escopos.ler_tokens(p) == {}
    assert escopos.ler_tokens(tmp_path / "nao-existe.json") == {}


def _chamar_mw(nome, escopos_tok, monkeypatch):
    import fastmcp.server.dependencies as dep
    tok = None if escopos_tok is None else SimpleNamespace(scopes=escopos_tok, client_id="client:x")
    monkeypatch.setattr(dep, "get_access_token", lambda: tok)
    ctx = SimpleNamespace(message=SimpleNamespace(name=nome))

    async def seguir(c):
        return "executou"
    return asyncio.run(escopos.EscopoMiddleware().on_call_tool(ctx, seguir))


def test_middleware_recusa_escrita_para_leitura(monkeypatch):
    from fastmcp.exceptions import ToolError
    assert _chamar_mw("search_vault", ["read"], monkeypatch) == "executou"
    with pytest.raises(ToolError, match="permission_denied"):
        _chamar_mw("write_note", ["read"], monkeypatch)
    assert _chamar_mw("write_note", ["master"], monkeypatch) == "executou"
    assert _chamar_mw("write_note", None, monkeypatch) == "executou"


def test_cli_create_list_revoke(tmp_path, monkeypatch, capsys):
    import delegation_core.config as config_mod
    from delegation_core import cli
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.json")
    a = lambda **k: SimpleNamespace(**{"acao": "list", "name": "", "write": False, "force": False, **k})  # noqa: E731
    assert cli.cmd_token(a(acao="create", name="codex")) == 0
    salvo = json.loads((tmp_path / "config.json").read_text())["client_tokens"]["codex"]
    assert salvo["scope"] == "read" and len(salvo["token"]) > 30
    assert cli.cmd_token(a(acao="create", name="codex")) == 1
    assert cli.cmd_token(a(acao="create", name="desk", write=True)) == 0
    assert json.loads((tmp_path / "config.json").read_text())["client_tokens"]["desk"]["scope"] == "write"
    cli.cmd_token(a(acao="list"))
    assert "codex" in capsys.readouterr().out
    assert cli.cmd_token(a(acao="revoke", name="codex")) == 0
    assert "codex" not in json.loads((tmp_path / "config.json").read_text())["client_tokens"]


def test_cli_ocr_setup_sem_tesseract_nao_quebra(monkeypatch, tmp_path):
    """Mesmo defeito que o test_cli pegou no token: `console` nao existe no modulo."""
    import shutil
    from delegation_core import cli
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert cli.cmd_ocr_setup(SimpleNamespace(langs="por", force=False)) == 1
