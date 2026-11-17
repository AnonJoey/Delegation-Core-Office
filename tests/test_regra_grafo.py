"""Regra grafo_desatualizado: grafo de repositorio git varios commits atras do HEAD."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

from delegation_core import vigia


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp_path, commits):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    shas = []
    for i in range(commits):
        (repo / f"f{i}.py").write_text(str(i))
        git(repo, "add", ".")
        git(repo, "commit", "-qm", f"c{i}")
        shas.append(git(repo, "rev-parse", "HEAD"))
    return repo, shas


def _ctx(tmp_path, grafos):
    gd = tmp_path / "graphs"
    reg = {}
    for nome, (fonte, commit) in grafos.items():
        (gd / nome).mkdir(parents=True)
        (gd / nome / "graph.json").write_text(json.dumps({"nodes": [], "built_at_commit": commit}))
        reg[nome] = {"source_path": str(fonte)}
    (tmp_path / "reg.json").write_text(json.dumps(reg))
    cfg = SimpleNamespace(graphs_dir=gd, graphs_registry_path=tmp_path / "reg.json")
    return SimpleNamespace(cfg=cfg)


def test_dispara_so_com_commits_suficientes(tmp_path, monkeypatch):
    repo, shas = _repo(tmp_path, 8)
    copia = tmp_path / "copia"
    copia.mkdir()
    monkeypatch.setattr("delegation_core.registro_grafos._load_registry",
                        lambda cfg: json.loads((tmp_path / "reg.json").read_text()))
    vigia._COMMIT_DO_GRAFO.clear()
    ctx = _ctx(tmp_path, {"velho": (repo, shas[1]), "quase": (repo, shas[3]), "em_dia": (repo, shas[-1]),
                          "sem_git": (copia, shas[0]), "sem_commit": (repo, None)})
    d = vigia.regra_grafo_desatualizado(ctx)
    assert [x.sujeito for x in d] == ["velho"]      # 6 atras; "quase" esta 4 atras
    assert d[0].detalhe["commits_atras"] == 6 and "graph_build_bg" in d[0].mensagem and "graph_changed_notes" in d[0].mensagem


def test_commit_lido_uma_vez_por_versao(tmp_path, monkeypatch):
    import os
    g = tmp_path / "graph.json"
    g.write_text(json.dumps({"built_at_commit": "abc"}))
    vigia._COMMIT_DO_GRAFO.clear()
    assert vigia._commit_do_grafo(g) == "abc"
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(AssertionError("releu")))
    assert vigia._commit_do_grafo(g) == "abc"
    monkeypatch.undo()
    g.write_text(json.dumps({"built_at_commit": "def"}))
    st = g.stat()
    os.utime(g, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert vigia._commit_do_grafo(g) == "def"


def test_regra_esta_na_lista_padrao():
    assert "grafo_desatualizado" in [r.nome for r in vigia.regras_padrao()]


def test_subpasta_conta_so_os_commits_dela(tmp_path, monkeypatch):
    repo, shas = _repo(tmp_path, 1)
    (repo / "painel").mkdir()
    (repo / "painel" / "a.js").write_text("1")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "painel")
    base = git(repo, "rev-parse", "HEAD")
    for i in range(6):                              # 6 commits fora do painel
        (repo / f"g{i}.py").write_text(str(i))
        git(repo, "add", ".")
        git(repo, "commit", "-qm", f"g{i}")
    monkeypatch.setattr("delegation_core.registro_grafos._load_registry",
                        lambda cfg: json.loads((tmp_path / "reg.json").read_text()))
    vigia._COMMIT_DO_GRAFO.clear()
    ctx = _ctx(tmp_path, {"painel": (repo / "painel", base), "raiz": (repo, base)})
    assert [x.sujeito for x in vigia.regra_grafo_desatualizado(ctx)] == ["raiz"]
