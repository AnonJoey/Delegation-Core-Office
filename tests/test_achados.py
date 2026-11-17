"""Achados do sonho: registro, descarte que vence, e a marca superseded_by na busca."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import sonho_vault
from delegation_core.sonho import RegistroDeAchados


@pytest.fixture
def reg(tmp_path):
    r = RegistroDeAchados(tmp_path / "a.sqlite3")
    yield r
    r.fechar()


def test_registrar_e_consultar_por_nota_velha(reg):
    reg.registrar("Decisions/02-09.md", "Fixes/26-09.md", "updates", "drop-in tira o BGE", "drop-in removido", em=1)
    reg.registrar("Decisions/02-09.md", "Fixes/27-09.md", "contradicts", "a", "b", em=2)
    r = reg.sobre(["Decisions/02-09.md", "Outra.md"])
    assert list(r) == ["Decisions/02-09.md"]
    assert [x["by"] for x in r["Decisions/02-09.md"]] == ["Fixes/27-09.md", "Fixes/26-09.md"]
    assert reg.sobre([]) == {}


def test_descarte_vence_o_proximo_sonho(reg):
    reg.registrar("v.md", "n.md", "updates", em=1)
    assert reg.descartar("v.md", "n.md") and not reg.descartar("v.md", "outra.md")
    reg.registrar("v.md", "n.md", "updates", "citacao nova", em=5)  # o sonho acha de novo
    assert reg.sobre(["v.md"]) == {}
    assert reg.todos(incluir_descartados=True)[0]["dismissed"] is True


def test_marcar_superadas_nos_acertos(tmp_path, monkeypatch):
    cfg = SimpleNamespace(sonho_enabled=True, achados_path=str(tmp_path / "a.sqlite3"))
    sonho_vault._ACHADOS.clear()
    sonho_vault.achados(cfg).registrar("velha.md", "nova.md", "updates", "antes", "agora")
    hits = [{"path": "velha.md"}, {"path": "outra.md"}]
    sonho_vault.marcar_superadas(cfg, hits)
    assert hits[0]["superseded_by"][0]["by"] == "nova.md" and "superseded_by" not in hits[1]
    sonho_vault._ACHADOS.clear()


def test_marcar_nunca_derruba_a_busca(monkeypatch):
    monkeypatch.setattr(sonho_vault, "achados", lambda cfg: (_ for _ in ()).throw(OSError("disco")))
    hits = [{"path": "a.md"}]
    sonho_vault.marcar_superadas(SimpleNamespace(), hits)
    assert hits == [{"path": "a.md"}]


class VaultFalso:
    def __init__(self, cfg):
        self.cfg = cfg

    def search(self, query, limit=5, scope="all", graph="", snippet_chars=800, client="", folder=""):
        return [{"path": "Decisions/02-09.md", "title": "d", "similarity": 0.7, "snippet": ""}]


def test_search_vault_e_ferramentas(tmp_path, monkeypatch):
    from delegation_core.config import Config
    cfg = Config(vault_path=str(tmp_path), vault_folders=["Decisions"], achados_path=str(tmp_path / "a.sqlite3"),
                 recordacao_enabled=False, busca_hibrida=False)
    sonho_vault._ACHADOS.clear()
    sonho_vault.achados(cfg).registrar("Decisions/02-09.md", "Fixes/26-09.md", "updates", "antes", "agora")
    monkeypatch.setattr(server, "_vault", VaultFalso(cfg))
    monkeypatch.setattr(server, "_engine", SimpleNamespace(cfg=cfg))
    monkeypatch.setattr(cfg, "route", lambda **k: "agent", raising=False)
    r = json.loads(asyncio.run(server.search_vault(query="gpu", scope="notes")))
    assert r["sources"][0]["superseded_by"][0]["new_says"] == "agora"
    assert len(json.loads(server.dream_findings())["findings"]) == 1
    assert json.loads(server.dream_dismiss(old="Decisions/02-09.md", new="Fixes/26-09.md"))["dismissed"]
    r = json.loads(asyncio.run(server.search_vault(query="gpu", scope="notes")))
    assert "superseded_by" not in r["sources"][0]
    assert json.loads(server.dream_dismiss(old="x", new="y"))["error_type"] == "not_found"
    sonho_vault._ACHADOS.clear()


def test_sonho_registra_o_achado_confirmado(tmp_path, monkeypatch):
    """O que o sonho confirma vai para o registro; o que cai na confirmacao, nao."""
    from delegation_core.config import Config
    import os, time
    raiz = tmp_path / "v"
    (raiz / "Fixes").mkdir(parents=True)
    (raiz / "Decisions").mkdir()
    (raiz / "Decisions" / "2026-09-02-velha.md").write_text("Decisao: colocar CUDA_VISIBLE_DEVICES vazio no drop-in cpu-embeddings.conf.")
    velho = time.time() - 30 * 86400
    os.utime(raiz / "Decisions" / "2026-09-02-velha.md", (velho, velho))
    hoje = time.strftime("%Y-%m-%d")
    (raiz / "Fixes" / f"{hoje}-nova.md").write_text("O drop-in cpu-embeddings.conf foi removido hoje.")
    cfg = Config(vault_path=str(raiz), vault_folders=["Fixes", "Decisions"], achados_path=str(tmp_path / "a.sqlite3"),
                 recordacao_path=str(tmp_path / "r.sqlite3"))
    sonho_vault._ACHADOS.clear(); sonho_vault._REGISTRO.clear()

    class V:
        def __init__(s): s.cfg = cfg
        def search(s, q, **k): return [{"path": f"Fixes/{hoje}-nova.md"}, {"path": "Decisions/2026-09-02-velha.md"}]

    def modelo(system, prompt):
        if system == sonho_vault.CONFIRMACAO:
            return json.dumps({"same_subject": True, "a_replaces_or_contradicts_b": True})
        return json.dumps({"relation": "updates", "claim_in_B": "CUDA_VISIBLE_DEVICES vazio no drop-in",
                           "claim_in_A": "O drop-in cpu-embeddings.conf foi removido", "confidence": 0.9})
    sonho_vault.sonhar(V(), modelo, dias=2)
    assert list(sonho_vault.achados(cfg).sobre(["Decisions/2026-09-02-velha.md"])) == ["Decisions/2026-09-02-velha.md"]
    sonho_vault._ACHADOS.clear(); sonho_vault._REGISTRO.clear()
