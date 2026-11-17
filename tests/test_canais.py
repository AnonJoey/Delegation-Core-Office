"""Canais de atualizacao e rollback, num repositorio git de verdade."""

from __future__ import annotations

import subprocess

import pytest

from delegation_core import canais, config, installer


def _g(raiz, *a):
    return subprocess.run(["git", "-C", str(raiz), *a], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    raiz = tmp_path / "src"
    raiz.mkdir()
    _g(raiz, "init", "-q", "-b", "main")
    _g(raiz, "config", "user.email", "t@t")
    _g(raiz, "config", "user.name", "t")
    for i, tag in enumerate(["v0.9.0", "v0.10.0", None]):
        (raiz / "f.txt").write_text(str(i))
        _g(raiz, "add", ".")
        _g(raiz, "commit", "-qm", f"c{i}")
        if tag:
            _g(raiz, "tag", tag)
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(installer, "CONFIG_DIR", tmp_path / "cfg")
    diario = []

    class Servico:
        is_up = staticmethod(lambda wait_seconds=0.0: True)
        stop = staticmethod(lambda timeout=None: {"status": "stopped"})
        start = staticmethod(lambda: {"status": "started"})
        install = staticmethod(lambda: {"status": "installed"})

    monkeypatch.setattr(installer, "service", Servico)
    monkeypatch.setattr(installer, "_pip_install", lambda r: (diario.append("pip"), (True, "ok"))[1])
    monkeypatch.setattr(installer, "refresh_shipped_files", lambda r: {})
    monkeypatch.setattr(installer, "stale_dist_copies", lambda: [])
    return raiz


def test_estavel_e_a_tag_de_versao_mais_nova_por_ordem_de_versao(repo):
    assert canais.tag_estavel(repo) == "v0.10.0", "v0.10 > v0.9, que a ordem alfabetica inverteria"
    assert canais.ref_para(repo, "stable") == ("v0.10.0", "")
    assert canais.ref_para(repo, "branch") == ("", "")
    assert "unknown" in canais.ref_para(repo, "nightly")[1]


def test_update_estavel_registra_e_rollback_volta(repo):
    topo = _g(repo, "rev-parse", "HEAD")
    r = installer.update(root=repo, ref="v0.10.0")
    assert r["status"] == "ok", r
    assert _g(repo, "rev-parse", "HEAD") == _g(repo, "rev-parse", "v0.10.0^{commit}")
    hist = canais.ler_historico()
    assert hist[-1]["sha"] == topo and hist[-1]["branch"] == "main" and hist[-1]["to"] == "v0.10.0"

    ref, erro = canais.ref_para(repo, "branch", reverter=True)
    assert (ref, erro) == (topo, "")
    assert installer.update(root=repo, ref=ref)["status"] == "ok"
    assert _g(repo, "rev-parse", "HEAD") == topo


def test_rollback_sem_historico(repo):
    assert "nothing to roll back" in canais.ref_para(repo, "branch", reverter=True)[1]


def test_ref_inexistente_falha_sem_trocar(repo):
    topo = _g(repo, "rev-parse", "HEAD")
    r = installer.update(root=repo, ref="v9.9.9")
    assert r["status"] == "failed" and "checkout" in r["detail"]
    assert _g(repo, "rev-parse", "HEAD") == topo
