"""Processos com dono, bloqueador, evidencia e vigia; claim atomico entre processos."""

from __future__ import annotations

import json
import multiprocessing
from datetime import datetime, timedelta

from delegation_core.tracker import ProcessTracker


def test_claim_exclusivo_e_liberacao(tmp_path):
    tr = ProcessTracker(tmp_path / "p.json")
    p = tr.create("deploy")
    assert tr.claim(p["id"], "codex")["process"]["owner"] == "codex"
    assert tr.claim(p["id"], "codex").get("process"), "pegar de novo o proprio e ok"
    r = tr.claim(p["id"], "desktop")
    assert r["error"].startswith("already claimed") and r["owner"] == "codex"
    assert "not desktop" in tr.release(p["id"], "desktop")["error"]
    tr.release(p["id"], "codex")
    assert tr.claim(p["id"], "desktop")["process"]["owner"] == "desktop"


def test_claim_velho_pode_ser_tomado(tmp_path):
    tr = ProcessTracker(tmp_path / "p.json")
    p = tr.create("x")
    tr.claim(p["id"], "codex")
    dados = json.loads((tmp_path / "p.json").read_text())
    velho = (datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds")
    dados[0]["claimed_at"] = dados[0]["updated"] = velho
    (tmp_path / "p.json").write_text(json.dumps(dados))
    r = tr.claim(p["id"], "desktop")
    assert r["process"]["owner"] == "desktop"
    assert "taken from codex" in r["process"]["notes"][-1]["text"]


def test_bloqueador_impede_claim_ate_ficar_pronto(tmp_path):
    tr = ProcessTracker(tmp_path / "p.json")
    a = tr.create("a")
    b = tr.create("b", blocked_by=[a["id"][:8]], parent=a["id"])
    assert b["blocked_by"] == [a["id"]] and b["parent"] == a["id"]
    assert tr.claim(b["id"], "c") == {"error": "blocked", "blocked_by": [a["id"]]}
    tr.update(a["id"], status="done", evidence="commit abc")
    assert tr.claim(b["id"], "c")["process"]["owner"] == "c"
    assert [x["id"] for x in tr.children(a["id"])] == [b["id"]]


def test_evidencia_e_verificacao(tmp_path):
    tr = ProcessTracker(tmp_path / "p.json")
    a, b = tr.create("a"), tr.create("b")
    tr.claim(a["id"], "c")
    pa = tr.update(a["id"], status="done")
    assert pa["verification"] == "missing_evidence" and "owner" not in pa, "feito solta o claim"
    pb = tr.update(b["id"], evidence="pytest 2456 passed", status="done")
    assert pb["verification"] == "verified"
    w = tr.watchdog()
    assert [x["id"] for x in w["done_without_evidence"]] == [a["id"]]


def test_vigia(tmp_path):
    tr = ProcessTracker(tmp_path / "p.json")
    a, b, c = tr.create("a"), tr.create("b"), tr.create("c")
    tr.update(a["id"], blocked_by=[b["id"]])
    tr.update(b["id"], blocked_by=[c["id"]])
    tr.update(c["id"], blocked_by=[a["id"]])
    d = tr.create("d", blocked_by=["proc_naoexiste"])
    e = tr.create("e")
    tr.update(e["id"], status="cancelled")
    f = tr.create("f", blocked_by=[e["id"]])
    tr.claim(tr.create("parado")["id"], "codex")
    dados = json.loads((tmp_path / "p.json").read_text())
    dados[-1]["updated"] = "2020-01-01T00:00:00"
    (tmp_path / "p.json").write_text(json.dumps(dados))
    w = tr.watchdog()
    assert len(w["cycles"]) == 1 and set(w["cycles"][0]) == {a["id"], b["id"], c["id"]}
    assert {(x["id"], x["reason"]) for x in w["bad_blockers"]} == {(d["id"], "missing"), (f["id"], "cancelled")}
    assert [x["name"] for x in w["stale"]] == ["parado"] and w["stale_claims"][0]["owner"] == "codex"


def test_ciclo_por_aresta_que_nao_e_a_primeira(tmp_path):
    tr = ProcessTracker(tmp_path / "p.json")
    a, b, c = tr.create("a"), tr.create("b"), tr.create("c")
    tr.update(a["id"], blocked_by=[c["id"], b["id"]])
    tr.update(b["id"], blocked_by=[a["id"]])
    assert len(tr.watchdog()["cycles"]) == 1


def _disputa(caminho, pid, nome, fila, largada):
    tr = ProcessTracker(caminho)
    largada.wait(30)
    fila.put((nome, "process" in tr.claim(pid, nome)))


def test_claim_atomico_entre_processos(tmp_path):
    """Doze processos de verdade disputam o mesmo claim: exatamente um ganha."""
    caminho = tmp_path / "p.json"
    pid = ProcessTracker(caminho).create("disputado")["id"]
    ctx = multiprocessing.get_context("spawn")
    fila, largada = ctx.Queue(), ctx.Event()
    ps = [ctx.Process(target=_disputa, args=(caminho, pid, f"agente{i}", fila, largada)) for i in range(12)]
    for p in ps:
        p.start()
    import time
    time.sleep(3)  # todos importados e parados na largada
    largada.set()
    for p in ps:
        p.join(60)
    ganhos = [n for n, ok in (fila.get() for _ in ps) if ok]
    assert len(ganhos) == 1
    assert ProcessTracker(caminho).get(pid)["owner"] == ganhos[0]
