"""Notas que citam codigo mudado desde o build do grafo."""

from __future__ import annotations

import asyncio
import json
import subprocess
from types import SimpleNamespace

import delegation_core.server as server
from delegation_core import codigo_vault
from delegation_core.ligacao_codigo import faixas_do_diff, nos_tocados

DIFF = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -12,0 +13,2 @@ def f():
@@ -30,3 +32,1 @@ def g():
diff --git a/novo.py b/novo.py
--- /dev/null
+++ b/novo.py
@@ -0,0 +1,5 @@
--- a/src/b.py
+++ b/src/b.py
@@ -7 +7 @@
"""


def test_faixas_do_diff():
    assert faixas_do_diff(DIFF) == {"src/a.py": [(12, 12), (30, 32)], "src/b.py": [(7, 7)]}
    assert faixas_do_diff("") == {}


def no(i, label, arq, linha, tipo="code"):
    return {"id": i, "label": label, "source_file": arq, "source_location": f"L{linha}", "file_type": tipo}


def test_nos_tocados_pelo_trecho_ate_o_proximo_no():
    nos = [no("arq", "a.py", "src/a.py", 1), no("f", "f()", "src/a.py", 10), no("g", "g()", "src/a.py", 25),
           no("h", "h()", "src/a.py", 40), no("r", "porque", "src/a.py", 31, "rationale"),
           no("b", "b()", "src/b.py", 1), no("x", "x()", "src/c.py", 1), {"id": "sem", "file_type": "code"}]
    t = nos_tocados(nos, {"src/a.py": [(12, 12), (30, 32)], "src/b.py": [(7, 7)]})
    assert t == {"f": [(12, 12)], "g": [(30, 32)], "b": [(7, 7)]}
    assert nos_tocados(nos, {"src/a.py": [(3, 3)]}) == {"arq": [(3, 3)]}      # antes da primeira funcao
    assert set(nos_tocados(nos, {"src/a.py": [(20, 45)]})) == {"f", "g", "h"}
    # mudanca na primeira linha de g e so de g, nao de f
    assert nos_tocados(nos, {"src/a.py": [(25, 25)]}) == {"g": [(25, 25)]}


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


def test_ponta_a_ponta(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    git(repo, "init", "-q"); git(repo, "config", "user.email", "t@t"); git(repo, "config", "user.name", "t")
    (repo / "src" / "m.py").write_text("import os\n\ndef detect_device():\n    return 1\n\ndef outra_coisa():\n    return 2\n")
    git(repo, "add", "."); git(repo, "commit", "-qm", "a")
    feito = git(repo, "rev-parse", "HEAD")
    (repo / "src" / "m.py").write_text("import os\n\ndef detect_device():\n    return 99\n\ndef outra_coisa():\n    return 2\n")
    git(repo, "commit", "-qam", "b")
    gd = tmp_path / "graphs" / "g"
    gd.mkdir(parents=True)
    (gd / "graph.json").write_text(json.dumps({"built_at_commit": feito, "nodes": [
        no("m", "m.py", "src/m.py", 1), no("d", "detect_device()", "src/m.py", 3), no("o", "outra_coisa()", "src/m.py", 6)]}))
    (tmp_path / "reg.json").write_text(json.dumps({"g": {"source_path": str(repo)}}))
    raiz = tmp_path / "v"
    (raiz / "Fixes").mkdir(parents=True)
    (raiz / "Fixes" / "d.md").write_text("O `detect_device()` devolvia 1.")
    (raiz / "Fixes" / "o.md").write_text("O `outra_coisa()` nao mudou.")
    cfg = SimpleNamespace(vault=raiz, graphs_dir=tmp_path / "graphs", graphs_registry_path=tmp_path / "reg.json",
                          codigo_path=str(tmp_path / "c.sqlite3"), codigo_enabled=True)
    codigo_vault._INDICE.clear(); codigo_vault._REVERSO.clear()
    from delegation_core import atencao
    atencao._CACHE_MUDADO.clear()
    [item] = atencao._codigo_mudado(cfg)
    assert item["tipo"] == "code_changed" and "`Fixes/d.md`" in item["texto"] and "`detect_device()`" in item["texto"]
    orig = codigo_vault.notas_de_codigo_mudado
    codigo_vault.notas_de_codigo_mudado = lambda *a, **k: 1 / 0     # cache: nao recalcula
    try:
        assert atencao._codigo_mudado(cfg) == [item]
    finally:
        codigo_vault.notas_de_codigo_mudado = orig
    atencao._CACHE_MUDADO.clear()
    r = codigo_vault.notas_de_codigo_mudado(cfg, "g")
    assert (r["commits"], r["nodes_changed"], r["notes_total"]) == (1, 1, 1)
    assert r["notes_to_review"][0] == {"note": "Fixes/d.md",
                                       "changed_code": [{"label": "detect_device()", "file": "src/m.py", "line": "L3"}]}
    assert "error" in codigo_vault.notas_de_codigo_mudado(cfg, "g", anterior=True)

    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(server, "_vault", SimpleNamespace(cfg=cfg))
    try:
        t = json.loads(asyncio.run(server.graph_changed_notes(name="g")))
        assert t["notes_total"] == 1
        assert json.loads(asyncio.run(server.graph_changed_notes(name="nada")))["error_type"] == "not_found"
        assert json.loads(asyncio.run(server.graph_changed_notes(name="g", previous=True)))["error_type"] == "failure"
    finally:
        mp.undo()
    codigo_vault._INDICE.clear(); codigo_vault._REVERSO.clear()
