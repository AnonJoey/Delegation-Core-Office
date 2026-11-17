"""Historico da nota no painel: rotas history, diff e restore, e o save que guarda a versao anterior."""

from __future__ import annotations

import http.client
import json

import pytest

from delegation_core import dashboard_api, historico_vault
from delegation_core.config import Config
from delegation_core.tracker import ProcessTracker
from tests._dashboard_auth import AUTH, TOKEN


class VaultFalso:
    def __init__(self, cfg):
        self.cfg = cfg

    def index_note(self, t, m):
        return True

    def stamp_indexed(self, r):
        pass


@pytest.fixture
def painel(monkeypatch, tmp_path):
    import delegation_core.config as config_mod
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.json")
    raiz = tmp_path / "vault"
    (raiz / "Fixes").mkdir(parents=True)
    (raiz / "Fixes" / "a.md").write_text("original\n")
    cfg = Config(vault_path=str(raiz), vault_folders=["Fixes"])
    for nome in ("_cfg", "_vault", "_tracker"):
        monkeypatch.setattr(dashboard_api, nome, None)
    # A API exige o bearer token desde o PR 42 do upstream, e serve_in_process le o token da
    # configuracao: com o de teste na configuracao, as requisicoes abaixo mandam AUTH.
    cfg.server_token = TOKEN
    historico_vault._INSTANCIAS.clear()
    servidor = dashboard_api.serve_in_process(cfg, VaultFalso(cfg), ProcessTracker(tmp_path / "p.json"), port=0)
    yield servidor.server_address[1], raiz, cfg
    servidor.shutdown()
    servidor.server_close()
    for h in historico_vault._INSTANCIAS.values():
        h.fechar()
    historico_vault._INSTANCIAS.clear()


def _req(porta, metodo, caminho, corpo=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
    dados = json.dumps(corpo).encode() if corpo is not None else None
    c.request(metodo, caminho, body=dados, headers={**AUTH, **({"Content-Type": "application/json"} if dados else {})})
    r = c.getresponse()
    body = json.loads(r.read())
    c.close()
    return r.status, body


def test_editar_no_painel_guarda_a_versao_anterior_e_restaura(painel):
    porta, raiz, _ = painel
    s, r = _req(porta, "POST", "/api/vault/note/save", {"path": "Fixes/a.md", "content": "estragada\n"})
    assert s == 200
    s, h = _req(porta, "GET", "/api/vault/note/history?path=Fixes/a.md")
    assert [v["origem"] for v in h["versions"]] == ["editada no painel", "antes de editar no painel"]
    s, d = _req(porta, "GET", "/api/vault/note/diff?path=Fixes/a.md&from=2&to=1")
    assert "-original" in d["diff"] and "+estragada" in d["diff"]
    s, r = _req(porta, "POST", "/api/vault/note/restore", {"path": "Fixes/a.md", "version": 2})
    assert s == 200 and (raiz / "Fixes" / "a.md").read_text() == "original\n"


def test_erros_das_rotas(painel):
    porta, _, _ = painel
    assert _req(porta, "GET", "/api/vault/note/history")[0] == 400
    assert _req(porta, "GET", "/api/vault/note/diff?path=Fixes/a.md&from=x")[0] == 400
    assert _req(porta, "GET", "/api/vault/note/diff?path=Fixes/a.md&from=5&to=1")[0] == 400
    assert _req(porta, "POST", "/api/vault/note/restore", {"path": "Fixes/a.md", "version": 0})[0] == 400
    assert _req(porta, "POST", "/api/vault/note/restore", {"path": "Fixes/a.md", "version": 9})[0] == 400


def test_historico_desligado(painel):
    porta, _, cfg = painel
    cfg.historico_enabled = False
    historico_vault._INSTANCIAS.clear()
    s, r = _req(porta, "GET", "/api/vault/note/history?path=Fixes/a.md")
    assert s == 400 and "disabled" in r["error"]


def test_as_rotas_do_js_existem_na_api():
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    js = (raiz / "dashboard" / "src" / "main.js").read_text(encoding="utf-8")
    api = (raiz / "src" / "delegation_core" / "dashboard_api.py").read_text(encoding="utf-8")
    for rota in ("/api/vault/note/history", "/api/vault/note/diff", "/api/vault/note/restore"):
        assert rota in js and f'"{rota}"' in api
