"""Facetas da busca: pasta no `where` do indice, e intervalo de datas pela data da nota."""

from __future__ import annotations

import asyncio
import json
import os
import time
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import facetas
from delegation_core.config import Config
from delegation_core.vault import VaultManager


class _Emb:
    """Embedding de brinquedo: frequencia de letras. Mesmo texto, mesmo vetor."""

    def __call__(self, input):
        out = []
        for t in input:
            v = [0.0] * 26
            for ch in t.lower():
                if "a" <= ch <= "z":
                    v[ord(ch) - 97] += 1
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out

    def embed_documents(self, input):
        return self(input)

    def embed_query(self, input):
        return self([input])[0] if isinstance(input, str) else self(list(input))

    def name(self):
        return "facetas"


@pytest.fixture
def vm(tmp_path):
    import chromadb
    cfg = Config(vault_path=str(tmp_path), vault_folders=["Decisions", "Fixes"], search_threshold=0.0)
    v = VaultManager(cfg)
    v.collection = chromadb.PersistentClient(path=str(tmp_path / "chroma")).get_or_create_collection(
        "facetas", embedding_function=_Emb(), metadata={"hnsw:space": "cosine"})
    v._initialized = True
    v._disk_state = None
    v._read_disk_state = lambda: None
    v._ensure_ready = lambda: None
    for rel in ("Decisions/2026-09-01-gpu.md", "Decisions/2026-09-20-gpu.md", "Fixes/2026-09-21-gpu.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("decisao sobre a placa de video gpu")
        v.index_note("decisao sobre a placa de video gpu", v.note_metadata(rel, rel, rel.split("/")[0], ""))
    return v


# ── funcoes puras ───────────────────────────────────────────────────────────

def test_data_da_nota_pela_ordem_nome_frontmatter_mtime():
    assert facetas.data_da_nota("Fixes/2026-09-01-x.md", "---\ndate: 2026-08-02\n---", 0) == "2026-09-01"
    assert facetas.data_da_nota("Tools/x.md", "---\ndate: '2026-08-02'\n---", 0) == "2026-08-02"
    assert facetas.data_da_nota("Tools/x.md", "", time.mktime((2026, 7, 5, 12, 0, 0, 0, 0, -1))) == "2026-07-05"


def test_data_valida():
    assert facetas.data_valida(" 2026-09-20 ") == "2026-09-20"
    assert facetas.data_valida("20/09/2026") is None and facetas.data_valida("2026-13-01") is None


def test_dentro_e_inclusivo():
    assert facetas.dentro("2026-09-20", "2026-09-20", "2026-09-20")
    assert not facetas.dentro("2026-09-19", "2026-09-20") and not facetas.dentro("2026-09-21", ate="2026-09-20")


def test_filtrar_por_data_poe_a_data_e_tira_o_que_sumiu(tmp_path):
    (tmp_path / "Fixes").mkdir()
    (tmp_path / "Fixes" / "2026-09-20-a.md").write_text("x")
    (tmp_path / "Fixes" / "2026-08-01-b.md").write_text("x")
    hits = [{"path": "Fixes/2026-09-20-a.md"}, {"path": "Fixes/2026-08-01-b.md"}, {"path": "Fixes/sumiu.md"}]
    r = facetas.filtrar_por_data(hits, tmp_path, desde="2026-09-01")
    assert r == [{"path": "Fixes/2026-09-20-a.md", "date": "2026-09-20"}]
    assert facetas.filtrar_por_data(hits, tmp_path) is hits


# ── pasta no indice ─────────────────────────────────────────────────────────

def test_search_por_pasta_filtra_no_indice(vm):
    todos = {h["path"] for h in vm.search("placa de video gpu", limit=10)}
    assert len(todos) == 3
    so = {h["path"] for h in vm.search("placa de video gpu", limit=10, folder="Fixes")}
    assert so == {"Fixes/2026-09-21-gpu.md"}


def test_pasta_compoe_com_escopo(vm):
    assert {h["path"] for h in vm.search("gpu", limit=10, scope="notes", folder="Decisions")} == {
        "Decisions/2026-09-01-gpu.md", "Decisions/2026-09-20-gpu.md"}


# ── search_vault ────────────────────────────────────────────────────────────

def _sv(vm, monkeypatch, **kw):
    monkeypatch.setattr(server, "_vault", vm)
    monkeypatch.setattr(server, "_engine", SimpleNamespace(cfg=vm.cfg))
    monkeypatch.setattr(vm.cfg, "route", lambda **k: "agent", raising=False)
    return json.loads(asyncio.run(server.search_vault(query="placa de video gpu", scope="notes", **kw)))


def test_search_vault_desde_e_pasta(vm, monkeypatch):
    r = _sv(vm, monkeypatch, since="2026-09-15", limit=5)
    assert sorted(s["path"] for s in r["sources"]) == ["Decisions/2026-09-20-gpu.md", "Fixes/2026-09-21-gpu.md"]
    assert all("date" in s for s in r["sources"])
    r = _sv(vm, monkeypatch, since="2026-09-15", folder="decisions", limit=5)
    assert [s["path"] for s in r["sources"]] == ["Decisions/2026-09-20-gpu.md"]


def test_search_vault_ate(vm, monkeypatch):
    r = _sv(vm, monkeypatch, until="2026-09-10", limit=5)
    assert [s["path"] for s in r["sources"]] == ["Decisions/2026-09-01-gpu.md"]


def test_search_vault_entrada_invalida(vm, monkeypatch):
    assert _sv(vm, monkeypatch, folder="naoexiste")["error_type"] == "invalid_input"
    assert _sv(vm, monkeypatch, since="ontem")["error_type"] == "invalid_input"


def test_search_vault_com_data_pede_mais_candidatos(vm, monkeypatch):
    pedidos = []
    orig = vm.search
    monkeypatch.setattr(vm, "search", lambda q, **kw: pedidos.append(kw["limit"]) or orig(q, **kw))
    _sv(vm, monkeypatch, since="2026-09-15", limit=2)
    assert pedidos == [30]
