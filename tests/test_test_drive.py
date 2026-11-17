from __future__ import annotations

import json
from pathlib import Path

import pytest

from delegation_core import config, test_drive


def test_prepara_isolado(tmp_path):
    r = test_drive.preparar(tmp_path / "td")
    cfg = json.loads(Path(r["config"]).read_text())
    assert cfg["engine_mode"] == "agent" and cfg["embed_device"] == "cpu" and cfg["dashboard_port"] == 0
    assert r["env"]["HOME"] == str((tmp_path / "td").resolve())
    assert Path(r["config"]) == Path(r["env"]["HOME"]) / ".delegation_core" / "config.json"
    assert len(list(Path(r["vault"]).rglob("*.md"))) == 2
    assert r["env"]["HF_HOME"] != str(Path(r["env"]["HOME"]) / ".cache" / "huggingface")


def test_copia_a_origem_e_nao_aponta_para_ela(tmp_path):
    origem = tmp_path / "origem"
    (origem / "Clientes").mkdir(parents=True)
    (origem / "Clientes" / "x.md").write_text("x")
    (origem / ".chroma_db").mkdir()
    r = test_drive.preparar(tmp_path / "td", origem=origem)
    assert (Path(r["vault"]) / "Clientes" / "x.md").read_text() == "x"
    assert not (Path(r["vault"]) / ".chroma_db").exists()
    assert "Clientes" in json.loads(Path(r["config"]).read_text())["vault_folders"]
    (Path(r["vault"]) / "Clientes" / "x.md").write_text("mudou")
    assert (origem / "Clientes" / "x.md").read_text() == "x"


def test_recusa_sobrepor_a_instalacao_real(tmp_path):
    vault_real = tmp_path / "real_vault"
    vault_real.mkdir()
    config.Config(vault_path=str(vault_real)).save()
    with pytest.raises(ValueError, match="overlaps"):
        test_drive.preparar(vault_real / "td")
    with pytest.raises(ValueError, match="overlaps"):
        test_drive.preparar(config.CONFIG_DIR / "td")
    ligacao = tmp_path / "atalho"
    ligacao.symlink_to(vault_real)
    with pytest.raises(ValueError, match="overlaps"):
        test_drive.preparar(ligacao / "td")
