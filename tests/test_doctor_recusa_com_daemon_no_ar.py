"""`doctor --rebuild-fts` e `--clean-orphans` escrevem no indice e recusam com o daemon no ar.

O doctor imprime essas duas linhas como `fix`, e quem as segue sem ler o resto abre um
segundo escritor no indice que o daemon segura. Diagnostico de 26/10/2026.
"""
import argparse

import pytest

from delegation_core import cli, daemon, doctor
from delegation_core.config import Config


def _args(**kw):
    base = dict(clean_orphans=False, include_backups=False, rebuild_fts=False)
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def chamadas(tmp_path, monkeypatch):
    chamadas = []
    cfg = Config(vault_path=str(tmp_path))
    monkeypatch.setattr(cli, "_graph_config", lambda: cfg)
    monkeypatch.setattr(doctor, "rebuild_fts", lambda c: chamadas.append("fts") or True)
    monkeypatch.setattr(doctor, "clean_orphan_segments", lambda c, include_backups=False: chamadas.append("orfas") or 0)
    monkeypatch.setattr(doctor, "run_all", lambda c: {"checks": [], "status": "ok", "counts": {"ok": 0, "warn": 0, "error": 0, "skip": 0}})
    return chamadas


@pytest.mark.parametrize("flag", ["rebuild_fts", "clean_orphans"])
def test_recusa_com_o_daemon_no_ar_e_nao_toca_no_indice(chamadas, monkeypatch, flag):
    monkeypatch.setattr(daemon, "is_listening", lambda cfg, *a, **k: True)
    with pytest.raises(SystemExit) as saiu:
        cli.cmd_doctor(_args(**{flag: True}))
    assert saiu.value.code == 1
    assert chamadas == []


def test_com_o_daemon_parado_o_reparo_roda(chamadas, monkeypatch):
    monkeypatch.setattr(daemon, "is_listening", lambda cfg, *a, **k: False)
    with pytest.raises(SystemExit) as saiu:
        cli.cmd_doctor(_args(rebuild_fts=True))
    assert saiu.value.code == 0 and chamadas == ["fts"]


def test_doctor_sem_flag_de_escrita_roda_com_o_daemon_no_ar(chamadas, monkeypatch):
    """So diagnostico: ler nao e o problema."""
    monkeypatch.setattr(daemon, "is_listening", lambda cfg, *a, **k: True)
    with pytest.raises(SystemExit) as saiu:
        cli.cmd_doctor(_args())
    assert saiu.value.code == 0 and chamadas == []
