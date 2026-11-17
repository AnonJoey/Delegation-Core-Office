"""O contrato MemoryAdapter do Paperclip sobre o vault: escopo, visibilidade, paginacao."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import adaptador_paperclip as ap
from delegation_core import historico_vault


class VaultFalso:
    def __init__(self, raiz):
        self.cfg = SimpleNamespace(vault=raiz, vault_folders=["Reference", "Fixes"], historico_enabled=True,
                                   redigir_segredos=True, paperclip_memory_folder="Reference")
        self.indexadas, self.apagadas = [], []

    def index_note(self, texto, meta):
        self.indexadas.append(meta["path"])
        return True

    def stamp_indexed(self, rels):
        pass

    def delete_notes(self, rels):
        self.apagadas.extend(rels)

    def find_notes_by_stem(self, nome):
        return [f for f in sorted(Path(self.cfg.vault).rglob("*.md")) if nome.lower() in f.stem.lower()]


@pytest.fixture
def vault(tmp_path, monkeypatch):
    (tmp_path / "v" / "Reference").mkdir(parents=True)
    historico_vault._INSTANCIAS.clear()
    v = VaultFalso(tmp_path / "v")
    monkeypatch.setattr(server, "_vault", v)
    yield v
    for h in historico_vault._INSTANCIAS.values():
        h.fechar()
    historico_vault._INSTANCIAS.clear()


ACME = {"companyId": "acme"}
ACME_A1 = {"companyId": "acme", "agentId": "a1"}


def todos(v):
    return lambda q, n: sorted(str(p.relative_to(v.cfg.vault)) for p in Path(v.cfg.vault).rglob("*.md"))


def test_escopo_obrigatorio(vault):
    with pytest.raises(ap.ErroDeEscopo):
        ap.capture(vault, {}, None, {"text": "x"})
    r = json.loads(server.memory_capture(scope={"agentId": "x"}, payload={"text": "x"}))
    assert "companyId" in json.dumps(r)


def test_capture_grava_nota_indexada_com_escopo(vault):
    r = ap.capture(vault, ACME_A1, {"kind": "run", "companyId": "acme", "runId": "r9"},
                   {"text": "Deploy usa porta 9090", "metadata": {"tema": "deploy"}})
    rel = r["records"][0]["providerRecordId"]
    assert rel.startswith("Reference/paperclip/acme/") and vault.indexadas == [rel]
    assert r["usage"][0]["provider"] == "delegation-core" and "latencyMs" in r["usage"][0]
    snip = ap.get(vault, r["records"][0], ACME_A1)
    assert snip["text"] == "Deploy usa porta 9090" and snip["source"]["runId"] == "r9"
    assert snip["metadata"] == {"tema": "deploy"}


def test_visibilidade_por_agente_e_empresa(vault):
    priv = ap.upsert_records(vault, ACME_A1, [{"text": "so do a1"}])["records"][0]
    comum = ap.upsert_records(vault, ACME, [{"text": "da empresa toda"}])["records"][0]
    outra = ap.upsert_records(vault, {"companyId": "globex"}, [{"text": "outra empresa"}])["records"][0]
    a2 = {"companyId": "acme", "agentId": "a2"}
    assert ap.get(vault, priv, a2) is None and ap.get(vault, priv, ACME_A1)
    assert ap.get(vault, comum, a2)["text"] == "da empresa toda"
    assert ap.get(vault, outra, ACME) is None
    textos = {s["text"] for s in ap.query(vault, a2, "x", buscar=todos(vault))["snippets"]}
    assert textos == {"da empresa toda"}
    textos = {i["text"] for i in ap.list_records(vault, ACME_A1)["items"]}
    assert textos == {"so do a1", "da empresa toda"}


def test_upsert_sobrescreve_pelo_handle(vault):
    h = ap.upsert_records(vault, ACME, [{"text": "v1", "summary": "fato"}])["records"][0]
    h2 = ap.upsert_records(vault, ACME, [{"text": "v2", "metadata": {"providerRecordId": h["providerRecordId"]}}])["records"][0]
    assert h2 == h and ap.get(vault, h, ACME)["text"] == "v2"
    with pytest.raises(ap.ErroDeEscopo):
        ap.upsert_records(vault, {"companyId": "globex"}, [{"text": "x", "metadata": {"providerRecordId": h["providerRecordId"]}}])


def test_query_intent_e_filtro(vault):
    ap.upsert_records(vault, ACME, [{"text": "A" * 2000, "metadata": {"tipo": "decisao"}},
                                    {"text": "B", "metadata": {"tipo": "fato"}}])
    pre = ap.query(vault, ACME, "x", intent="agent_preamble", buscar=todos(vault))["snippets"]
    assert max(len(s["text"]) for s in pre) == 400
    browse = ap.query(vault, ACME, "x", intent="browse", buscar=todos(vault))["snippets"]
    assert all(s["text"] == "" and s["handle"] for s in browse)
    f = ap.query(vault, ACME, "x", metadata_filter={"tipo": "fato"}, buscar=todos(vault))["snippets"]
    assert [s["text"] for s in f] == ["B"]


def test_list_pagina(vault):
    for i in range(5):
        ap.upsert_records(vault, ACME, [{"text": f"r{i}"}])
    p1 = ap.list_records(vault, ACME, limit=2)
    p2 = ap.list_records(vault, ACME, cursor=p1["nextCursor"], limit=2)
    p3 = ap.list_records(vault, ACME, cursor=p2["nextCursor"], limit=2)
    vistos = [i["text"] for p in (p1, p2, p3) for i in p["items"]]
    assert sorted(vistos) == [f"r{i}" for i in range(5)] and "nextCursor" not in p3


def test_forget_so_no_proprio_escopo_e_restauravel(vault):
    h = ap.upsert_records(vault, ACME, [{"text": "apagar"}])["records"][0]
    with pytest.raises(ap.ErroDeEscopo):
        ap.forget(vault, [h], {"companyId": "globex"})
    r = ap.forget(vault, [h], ACME)
    assert r["forgotten"] == [h["providerRecordId"]] and vault.apagadas == [h["providerRecordId"]]
    assert ap.get(vault, h, ACME) is None
    assert any((Path(vault.cfg.vault) / ".lixeira").rglob("*.md"))


def test_caminho_que_escapa_da_empresa(vault):
    (Path(vault.cfg.vault) / "Fixes").mkdir()
    (Path(vault.cfg.vault) / "Fixes" / "segredo.md").write_text("nao e da memoria")
    assert ap.get(vault, {"providerRecordId": "Fixes/segredo.md"}, ACME) is None
    assert ap.get(vault, {"providerRecordId": "../../etc/passwd"}, ACME) is None


def test_ferramentas_mcp(vault, monkeypatch):
    monkeypatch.setattr(server, "_buscar_caminhos", lambda q, n, e, p: todos(vault)(q, n))
    r = json.loads(server.memory_upsert(scope=ACME, records=[{"text": "via mcp"}]))
    h = r["records"][0]
    q = json.loads(asyncio.run(server.memory_query(scope=ACME, query="via")))
    assert q["snippets"][0]["text"] == "via mcp"
    assert json.loads(server.memory_get(handle=h, scope=ACME))["text"] == "via mcp"
    assert json.loads(server.memory_list(scope=ACME))["items"][0]["handle"] == h
    assert json.loads(server.memory_forget(handles=[h], scope=ACME))["forgotten"]
