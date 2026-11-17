from __future__ import annotations

import asyncio
import json
import os
import time
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import cartoes, standup
from delegation_core.tracker import ProcessTracker


@pytest.fixture
def raiz(tmp_path):
    r = tmp_path / "vault"
    (r / "Fixes").mkdir(parents=True)
    (r / "Fixes" / "a.md").write_text("a")
    (r / "Fixes" / "b.md").write_text("b")
    return r


def test_cartao_so_avisa_quando_muda(raiz):
    cartoes.salvar("incidentes", "incidente aberto")
    resultado = [["Fixes/a.md"]]
    buscar = lambda card: resultado[0]  # noqa: E731
    r = cartoes.atualizar(buscar, raiz, "codex")
    assert r["changed"] == 1 and r["cards"][0]["first_read"]
    assert cartoes.atualizar(buscar, raiz, "codex")["changed"] == 0
    assert cartoes.atualizar(buscar, raiz, "desktop")["changed"] == 1, "a novidade e por leitor"

    resultado[0] = ["Fixes/b.md", "Fixes/a.md"]
    c = cartoes.atualizar(buscar, raiz, "codex")["cards"][0]
    assert c["changed"] and c["new"] == ["Fixes/b.md"] and c["gone"] == []

    st = (raiz / "Fixes" / "a.md").stat()
    os.utime(raiz / "Fixes" / "a.md", (st.st_atime, st.st_mtime + 100))
    assert cartoes.atualizar(buscar, raiz, "codex")["changed"] == 1, "nota editada conta"


def test_cartao_inexistente_e_apagar(raiz):
    assert "error" in cartoes.atualizar(lambda c: [], raiz, "x", "nao")
    cartoes.salvar("c", "q")
    assert cartoes.apagar("c") and not cartoes.apagar("c")
    with pytest.raises(ValueError):
        cartoes.salvar("", "q")


def test_ferramentas_de_cartao(raiz, monkeypatch):
    class V:
        cfg = SimpleNamespace(vault=raiz)

        def search(self, q, limit=5, scope="all", snippet_chars=800, folder="", **kw):
            assert snippet_chars == 1
            return [{"path": "Fixes/a.md"}]
    monkeypatch.setattr(server, "_vault", V())
    monkeypatch.setattr(server.busca_hibrida, "aplicavel", lambda *a: False)
    monkeypatch.setattr(server, "_default_scope", lambda: "notes")
    assert json.loads(server.status_card_save(name="x", query="q"))["status"] == "ok"
    r = json.loads(asyncio.run(server.status_cards()))
    assert r["cards"][0]["paths"] == ["Fixes/a.md"]
    assert json.loads(asyncio.run(server.status_cards()))["changed"] == 0
    assert "not found" in server.status_card_delete(name="y")


def test_standup(raiz):
    hoje = time.strftime("%Y-%m-%d")
    (raiz / "Fixes" / f"{hoje}-nova.md").write_text("n")
    velha = raiz / "Fixes" / "2020-01-01-velha.md"
    velha.write_text("v")
    os.utime(velha, (time.time() - 10 * 86400,) * 2)
    cfg = SimpleNamespace(vault=raiz, vault_folders=["Fixes"], livro_enabled=False)
    tr = ProcessTracker(raiz.parent / "p.json")
    p = tr.create("deploy cliente X")
    tr.update(p["id"], note="subiu")
    tr.create("outro")
    s = standup.montar(cfg, tr, 24, projeto="")
    assert f"Fixes/{hoje}-nova.md" in s["notes"]["created"]
    assert "Fixes/2020-01-01-velha.md" not in s["notes"]["created"] + s["notes"]["modified"]
    assert {x["name"] for x in s["processes"]} == {"deploy cliente X", "outro"}
    s = standup.montar(cfg, tr, 24, projeto="cliente x")
    assert [x["new_notes"] for x in s["processes"]] == [["subiu"]]
    assert s["pending_approvals"] == 0 and s["pending_proposals"] == 0


def test_cartao_usa_a_busca_hibrida_quando_o_search_vault_usaria(monkeypatch):
    """O defeito do test-drive: so a densa, o cartao divergia do search_vault."""
    chamadas = []
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=SimpleNamespace()))
    monkeypatch.setattr(server.busca_hibrida, "aplicavel", lambda *a: True)
    monkeypatch.setattr(server.busca_hibrida, "buscar",
                        lambda v, q, lim, esc, sn, pasta: chamadas.append(q) or [{"path": "Fixes/h.md"}])
    monkeypatch.setattr(server, "_default_scope", lambda: "notes")
    assert server._buscar_cartao({"query": "porta"}) == ["Fixes/h.md"] and chamadas == ["porta"]
