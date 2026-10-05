"""Tarefa exclusiva com argumentos diferentes entra na fila; com os mesmos, junta.

Defeito medido em 05/10/2026: ingest_folder(rtk) e ingest_folder(headroom)
seguidos devolveram o mesmo job_id e so o rtk foi indexado."""

from __future__ import annotations

import threading
import time

from delegation_core import jobs


def _espera(jid, estado="done", limite=5.0):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if jobs.get(jid)["status"] == estado:
            return True
        time.sleep(0.01)
    return False


def test_argumentos_diferentes_viram_fila_e_os_dois_rodam():
    solta = threading.Event()
    feitos, ativos, pico = [], [0], [0]

    def trabalho(pasta):
        ativos[0] += 1
        pico[0] = max(pico[0], ativos[0])
        solta.wait(5)
        feitos.append(pasta)
        ativos[0] -= 1
        return pasta

    a = jobs.submit("ingest_folder", trabalho, "/rtk")
    b = jobs.submit("ingest_folder", trabalho, "/headroom")
    assert a != b, "o segundo pedido nao pode sumir dentro do primeiro"
    assert jobs.get(b)["status"] == "queued"
    c = jobs.submit("ingest_folder", trabalho, "/rtk")
    assert c == a and jobs.get(a)["pedidos_coalescidos"] == 1, "mesmo pedido ainda junta"
    solta.set()
    assert _espera(a) and _espera(b)
    assert sorted(feitos) == ["/headroom", "/rtk"] and pico[0] == 1, "nunca dois ao mesmo tempo"
    assert jobs.get(b)["result"] == "/headroom"


def test_tarefa_nao_exclusiva_nao_entra_em_fila():
    ev = threading.Event()
    a = jobs.submit("relink_folder", lambda p: ev.wait(5), "A")
    b = jobs.submit("relink_folder", lambda p: ev.wait(5), "B")
    assert jobs.get(a)["status"] == jobs.get(b)["status"] == "running"
    ev.set()
    assert _espera(a) and _espera(b)
