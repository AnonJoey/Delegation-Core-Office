"""Ask no painel: rota /api/ask chama o mesmo ask_vault do agente."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import delegation_core.server as server
from delegation_core import painel_resposta


def test_pergunta_vai_para_o_ask_vault(monkeypatch):
    vistas = []

    async def ask_falso(question):
        vistas.append(question)
        return json.dumps({"found": True, "claims": [], "seconds": 1.0})
    monkeypatch.setattr(server, "_vault", SimpleNamespace())
    monkeypatch.setattr(server, "ask_vault", ask_falso)
    assert painel_resposta.perguntar("  qual porta?  ") == {"found": True, "claims": [], "seconds": 1.0}
    assert vistas == ["qual porta?"]
    assert "required" in painel_resposta.perguntar("   ")["error"]


def test_fora_do_daemon_explica(monkeypatch):
    monkeypatch.setattr(server, "_vault", None)
    assert "inside the daemon" in painel_resposta.perguntar("x")["error"]


def test_rota_nas_duas_pontas():
    raiz = Path(__file__).resolve().parents[1]
    js = (raiz / "dashboard" / "src" / "main.js").read_text(encoding="utf-8")
    api = (raiz / "src" / "delegation_core" / "dashboard_api.py").read_text(encoding="utf-8")
    html = (raiz / "dashboard" / "src" / "index.html").read_text(encoding="utf-8")
    assert '"/api/ask"' in js and '"/api/ask"' in api and 'id="vector-ask-btn"' in html


def test_fatos_no_painel(tmp_path, monkeypatch):
    from delegation_core import fatos_vault
    from delegation_core.fatos import Fato
    cfg = SimpleNamespace(fatos_enabled=True, fatos_path=str(tmp_path / "f.sqlite3"))
    fatos_vault._ARMAZEM.clear()
    arm = fatos_vault.armazem(cfg)
    arm.substituir("a.md", "2026-08-01", "h", [Fato("llama.cpp", "port", "8080")])
    arm.substituir("b.md", "2026-09-20", "h", [Fato("llama.cpp", "port", "8181")])
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=cfg))
    r = painel_resposta.fatos("llama port")
    assert r["groups"][0]["current"] == "8181" and r["stats"]["notes"] == 2
    assert painel_resposta.fatos(divergentes=True)["groups"][0]["conflict"][0]["value"] == "8181"
    cfg.fatos_enabled = False
    assert "disabled" in painel_resposta.fatos()["error"]
    monkeypatch.setattr(server, "_vault", None)
    assert "inside the daemon" in painel_resposta.fatos()["error"]
    fatos_vault._ARMAZEM.clear()


def test_rota_de_fatos_nas_duas_pontas():
    raiz = Path(__file__).resolve().parents[1]
    js = (raiz / "dashboard" / "src" / "main.js").read_text(encoding="utf-8")
    api = (raiz / "src" / "delegation_core" / "dashboard_api.py").read_text(encoding="utf-8")
    assert "/api/facts?" in js and '"/api/facts"' in api


def test_achado_pelo_painel(monkeypatch):
    chamadas = []

    async def aplicar(old, new):
        chamadas.append(("apply", old, new)); return json.dumps({"applied": True})

    async def descartar(old, new):
        chamadas.append(("dismiss", old, new)); return json.dumps({"dismissed": True})
    monkeypatch.setattr(server, "_vault", SimpleNamespace())
    monkeypatch.setattr(server, "dream_apply", aplicar)
    monkeypatch.setattr(server, "dream_dismiss", descartar)
    assert painel_resposta.achado("v.md", "n.md", "apply") == {"applied": True}
    assert painel_resposta.achado("v.md", "n.md", "dismiss") == {"dismissed": True}
    assert "action must be" in painel_resposta.achado("v.md", "n.md", "apagar")["error"]
    assert "action must be" in painel_resposta.achado("", "n.md", "apply")["error"]
    assert chamadas == [("apply", "v.md", "n.md"), ("dismiss", "v.md", "n.md")]


def test_item_superado_leva_old_e_new(tmp_path):
    from delegation_core import atencao, sonho_vault
    cfg = SimpleNamespace(sonho_enabled=True, achados_path=str(tmp_path / "a.sqlite3"))
    sonho_vault._ACHADOS.clear()
    sonho_vault.achados(cfg).registrar("v.md", "n.md", "updates")
    [i] = atencao._achados(cfg)
    assert (i["old"], i["new"]) == ("v.md", "n.md")
    sonho_vault._ACHADOS.clear()
    raiz = Path(__file__).resolve().parents[1]
    assert '"/api/dream"' in (raiz / "dashboard" / "src" / "main.js").read_text(encoding="utf-8")
    assert '"/api/dream"' in (raiz / "src" / "delegation_core" / "dashboard_api.py").read_text(encoding="utf-8")
