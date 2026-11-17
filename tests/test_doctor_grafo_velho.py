"""Grafo construido antes de commits que a fonte recebeu depois.

## O caso real, medido em 26/09/2026

O grafo do `delegation-core` fora construido em 06/08 e a fonte recebera
commits ate 24/09:

| | nos | arestas |
|---|---|---|
| grafo no vault, de 06/08 | 2.121 | 4.574 |
| codigo de hoje | 6.140 | 11.143 |

A base quase **triplicou**, e 122 artigos indexados descreviam a versao de
agosto. Nada falha nesse estado, que e por isso que e checagem de doctor: os
artigos estao la, legiveis, indexados e errados.

Eu achei isso por acaso, olhando o registro. Esta checagem e a versao que acha
sempre.

## Git de verdade, e nao duble

Os testes montam repositorios git reais com data de commit controlada. Um
duble de `subprocess.run` provaria que o codigo trata a saida que EU inventei,
e nao a que o git produz, e a checagem inteira depende do formato de
`git log --format=%cd --date=short`.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from delegation_core import doctor
from delegation_core.config import Config


def _repo(caminho, data: str):
    """Um repo git com um commit na data pedida."""
    caminho.mkdir(parents=True, exist_ok=True)
    amb = {"GIT_AUTHOR_DATE": f"{data}T12:00:00", "GIT_COMMITTER_DATE": f"{data}T12:00:00"}
    def git(*args):
        subprocess.run(["git", "-C", str(caminho), *args], check=True,
                       capture_output=True, env={**__import__("os").environ, **amb})
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (caminho / "a.py").write_text("x = 1\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "um")
    return caminho


@pytest.fixture(autouse=True)
def config_isolado(tmp_path, monkeypatch):
    """`graphs_registry_path` deriva de `CONFIG_DIR`, entao e CONFIG_DIR que o
    teste move. Mexer na propriedade da classe nao e possivel e nem seria
    honesto: o teste passaria a exercitar um caminho que producao nao tem."""
    import delegation_core.config as config_mod
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path / "cfgdir")
    (tmp_path / "cfgdir").mkdir(parents=True, exist_ok=True)


def _cfg_com(tmp_path, registro: dict) -> Config:
    cfg = Config(vault_path=str(tmp_path / "vault"))
    cfg.graphs_registry_path.write_text(json.dumps(registro), encoding="utf-8")
    return cfg


def test_sem_registro_nao_ha_o_que_checar(tmp_path):
    cfg = Config(vault_path=str(tmp_path / "vault"))
    assert not cfg.graphs_registry_path.exists()
    assert doctor.check_grafo_desatualizado(cfg)["status"] == "ok"


def test_grafo_construido_DEPOIS_do_ultimo_commit_passa(tmp_path):
    fonte = _repo(tmp_path / "fonte", "2026-08-01")
    cfg = _cfg_com(tmp_path, {"g": {"source_path": str(fonte),
                                    "built_at": "2026-09-01T10:00:00"}})
    assert doctor.check_grafo_desatualizado(cfg)["status"] == "ok"


def test_grafo_construido_ANTES_de_commits_novos_avisa(tmp_path):
    """O caso real, reproduzido.

    Conferido por mutacao: inverter a comparacao de datas derruba este teste
    junto com o de cima.
    """
    fonte = _repo(tmp_path / "fonte", "2026-09-24")
    cfg = _cfg_com(tmp_path, {"delegation-core": {
        "source_path": str(fonte), "built_at": "2026-08-06T10:00:00",
        "vault_paths": ["a.md", "b.md"]}})
    r = doctor.check_grafo_desatualizado(cfg)

    assert r["status"] == "warn"
    assert "delegation-core" in r["detail"]
    assert "2026-09-24" in r["detail"], "o aviso tem que dizer ate quando a fonte andou"
    assert "2 notas" in r["detail"], "e quantas notas do vault descrevem a versao velha"


def test_o_aviso_diz_que_as_notas_do_vault_estao_velhas(tmp_path):
    """Sem isso, quem le pensa que e so refazer o grafo e nao percebe que ha
    conteudo errado indexado no vault."""
    fonte = _repo(tmp_path / "fonte", "2026-09-24")
    cfg = _cfg_com(tmp_path, {"g": {"source_path": str(fonte),
                                    "built_at": "2026-08-06T10:00:00"}})
    assert "vault" in doctor.check_grafo_desatualizado(cfg)["fix"].lower()


def test_fonte_sem_git_nao_e_acusada(tmp_path):
    """Pasta sem `.git` nao tem como dizer quando mudou de forma confiavel.

    mtime muda por copia, por backup e por editor sem nada ter mudado de
    verdade, e acusar com base nisso daria aviso falso, que e pior que nao
    avisar.
    """
    fonte = tmp_path / "sem_git"
    fonte.mkdir()
    (fonte / "a.py").write_text("x = 1\n", encoding="utf-8")
    cfg = _cfg_com(tmp_path, {"g": {"source_path": str(fonte),
                                    "built_at": "2026-01-01T10:00:00"}})
    assert doctor.check_grafo_desatualizado(cfg)["status"] == "ok"


def test_subpasta_de_repo_nao_herda_a_data_do_pai(tmp_path):
    """O caso que a guarda de `.git` protege, e que a mutacao revelou faltando.

    `git -C <subpasta>` FUNCIONA quando a subpasta esta dentro de um repo: ele
    sobe ate a raiz e responde o ultimo commit do PAI. Sem a checagem de
    `.git`, um grafo de `projeto/docs` seria acusado de velho toda vez que o
    `projeto` inteiro recebesse um commit, mesmo com a pasta `docs` intocada.

    Nao e hipotetico: o registro desta maquina tem `graphify/docs`,
    `hermes-agent/docs` e `openclaw/docs`.

    Conferido por mutacao: tirar a checagem de `.git` derruba este teste.
    """
    pai = _repo(tmp_path / "pai", "2026-09-24")
    sub = pai / "docs"
    sub.mkdir()
    (sub / "a.md").write_text("x\n", encoding="utf-8")

    cfg = _cfg_com(tmp_path, {"g": {"source_path": str(sub),
                                    "built_at": "2026-08-06T10:00:00"}})
    r = doctor.check_grafo_desatualizado(cfg)
    assert r["status"] == "ok", (
        "a subpasta nao tem .git proprio; acusa-la seria atribuir a ela o "
        f"commit do repo pai. Veio: {r.get('detail')}")


def test_e_aviso_e_nunca_erro(tmp_path):
    """Grafo velho e comum e as vezes deliberado, como base de referencia
    congelada de proposito. `doctor` sai com codigo 1 em erro."""
    fonte = _repo(tmp_path / "fonte", "2026-09-24")
    cfg = _cfg_com(tmp_path, {"g": {"source_path": str(fonte),
                                    "built_at": "2026-08-06T10:00:00"}})
    assert doctor.check_grafo_desatualizado(cfg)["status"] != "error"


def test_a_checagem_entra_no_run_all():
    """Uma checagem fora do `run_all` nao checa nada de ninguem.

    Conferido por mutacao: tirar a linha derruba este teste.
    """
    import inspect

    assert "check_grafo_desatualizado" in inspect.getsource(doctor.run_all)
