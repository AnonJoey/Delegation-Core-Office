from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import perguntas
from delegation_core.perguntas import ErroDePergunta


@pytest.fixture
def raiz(tmp_path):
    r = tmp_path / "vault"
    (r / "Decisions").mkdir(parents=True)
    (r / "Decisions" / "a.md").write_text("a")
    (r / "Decisions" / "b.md").write_text("b")
    return r


def test_ciclo_completo(raiz):
    q = perguntas.registrar(raiz, "O cliente X renova em janeiro?", "high", "contrato",
                            apoio=["Decisions/a.md"], passos=["perguntar ao financeiro"])
    assert q["revision"] == 1 and q["status"] == "open"
    q = perguntas.atualizar(raiz, q["id"], 1, estado="investigating", contra=["Decisions/b.md"])
    assert q["revision"] == 2 and q["contradicting"] == ["Decisions/b.md"]
    with pytest.raises(ErroDePergunta, match="conflict"):
        perguntas.atualizar(raiz, q["id"], 1, severidade="low")
    with pytest.raises(ErroDePergunta, match="absence of contrary evidence"):
        perguntas.responder(raiz, q["id"], 2, "sim", [])
    r = perguntas.responder(raiz, q["id"][:6], 2, "Sim, ate julho", ["Decisions/a.md"])
    assert r["status"] == "answered" and r["resolution"]["evidence"] == ["Decisions/a.md"]
    with pytest.raises(ErroDePergunta, match="already answered"):
        perguntas.responder(raiz, q["id"], 3, "de novo", ["Decisions/a.md"])
    assert perguntas.listar("open") == [] and len(perguntas.listar("answered")) == 1


def test_evidencia_tem_que_existir_e_estar_no_vault(raiz):
    with pytest.raises(ErroDePergunta, match="existing vault note"):
        perguntas.registrar(raiz, "q", apoio=["Decisions/nao-existe.md"])
    with pytest.raises(ErroDePergunta, match="existing vault note"):
        perguntas.registrar(raiz, "q", apoio=["../../etc/passwd"])
    with pytest.raises(ErroDePergunta, match="severity"):
        perguntas.registrar(raiz, "q", "urgente")


def test_ordem_e_evidencia_perdida(raiz):
    perguntas.registrar(raiz, "baixa", "low")
    perguntas.registrar(raiz, "alta", "high", apoio=["Decisions/b.md"])
    (raiz / "Decisions" / "b.md").unlink()
    itens = perguntas.listar("open", raiz=raiz)
    assert [i["question"] for i in itens] == ["alta", "baixa"]
    assert itens[0]["missing_evidence"] == ["Decisions/b.md"]


def test_ferramentas(raiz, monkeypatch):
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=SimpleNamespace(vault=raiz)))
    q = json.loads(server.question_record(question="Q?", supporting=["Decisions/a.md"]))
    r = json.loads(server.question_resolve(question_id=q["id"], expected_revision=1,
                                                        answer="x", evidence=[]))
    assert "evidence" in r["error"]
    assert json.loads(server.question_list())["count"] == 1
    u = json.loads(server.question_update(question_id=q["id"], expected_revision=1, status="answered"))
    assert "question_resolve" in u["error"]
