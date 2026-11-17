"""Export sem segredo, import com plano, troca de caminho, backup antes de sobrescrever."""

from __future__ import annotations

import json
import zipfile
from types import SimpleNamespace

import pytest

from delegation_core import config, portabilidade


@pytest.fixture
def instalacao(tmp_path):
    vault = tmp_path / "home_a" / "vault"
    (vault / "Decisions").mkdir(parents=True)
    (vault / "Decisions" / "d.md").write_text("# d\n")
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian" / "x.md").write_text("oculto")
    cfg = config.Config(vault_path=str(vault), server_token="TOKEN-SECRETO",
                        client_tokens={"codex": {"token": "TOKEN-CLIENTE-CODEX", "scope": "read"}})
    cfg.save()
    reg = {str(tmp_path / "home_a" / "docs"): {"files": 3}}
    (config.CONFIG_DIR / "ingested_sources.json").write_text(json.dumps(reg))
    (config.CONFIG_DIR / "avaliacao").mkdir()
    (config.CONFIG_DIR / "avaliacao" / "consultas.json").write_text("[]")
    return tmp_path, vault


def test_export_tira_segredo(instalacao, tmp_path):
    r = portabilidade.exportar(tmp_path / "pac.zip")
    assert set(r["scrubbed_keys"]) == {"server_token", "client_tokens"}
    with zipfile.ZipFile(tmp_path / "pac.zip") as z:
        tudo = b"".join(z.read(n) for n in z.namelist())
        nomes = set(z.namelist())
    assert b"TOKEN-SECRETO" not in tudo and b"TOKEN-CLIENTE-CODEX" not in tudo
    assert {"manifest.json", "config.json", "state/ingested_sources.json",
            "state/avaliacao/consultas.json"} <= nomes
    assert not any(n.startswith("vault/") for n in nomes)


def test_export_com_vault_pula_oculto(instalacao, tmp_path):
    r = portabilidade.exportar(tmp_path / "pac.zip", com_vault=True)
    assert r["vault_notes"] == 1


def test_import_sem_apply_nao_escreve_e_com_apply_guarda_o_anterior(instalacao, tmp_path):
    base, vault = instalacao
    portabilidade.exportar(tmp_path / "pac.zip")
    antigo, novo = str(base / "home_a"), str(base / "home_b")
    reg_antes = (config.CONFIG_DIR / "ingested_sources.json").read_text()
    r = portabilidade.importar(tmp_path / "pac.zip", [(antigo, novo)])
    assert not r["applied"] and (config.CONFIG_DIR / "ingested_sources.json").read_text() == reg_antes
    assert {p["action"] for p in r["plan"]} == {"replace"}

    r = portabilidade.importar(tmp_path / "pac.zip", [(antigo, novo)], aplicar=True)
    assert r["applied"] and r["backup_dir"]
    cfg = config.Config.load()
    assert cfg.vault_path == str(base / "home_b" / "vault")
    assert cfg.server_token == "TOKEN-SECRETO", "o segredo da maquina de destino fica"
    reg = json.loads((config.CONFIG_DIR / "ingested_sources.json").read_text())
    assert list(reg) == [str(base / "home_b" / "docs")]
    from pathlib import Path
    assert json.loads((Path(r["backup_dir"]) / "ingested_sources.json").read_text()) == json.loads(reg_antes)


def test_troca_de_prefixo_nao_pega_meio_de_nome():
    m = [("/home/a", "/home/b")]
    assert portabilidade._trocar("/home/ab/x", m) == "/home/ab/x"
    assert portabilidade._trocar("/home/a/x", m) == "/home/b/x"
    assert portabilidade._trocar({"/home/a": ["/home/a/y"]}, m) == {"/home/b": ["/home/b/y"]}


def test_pacote_adulterado_e_recusado(instalacao, tmp_path):
    portabilidade.exportar(tmp_path / "pac.zip")
    with zipfile.ZipFile(tmp_path / "pac.zip") as z:
        itens = {n: z.read(n) for n in z.namelist()}
    itens["config.json"] = itens["config.json"].replace(b"vault", b"VAULT")
    with zipfile.ZipFile(tmp_path / "ruim.zip", "w") as z:
        for n, b in itens.items():
            z.writestr(n, b)
    with pytest.raises(ValueError, match="checksum"):
        portabilidade.importar(tmp_path / "ruim.zip")


def test_caminho_que_escapa_e_recusado(tmp_path):
    man = {"format": "delegation-core-export/1", "files": {"state/../../fora.json": "x"}}
    with zipfile.ZipFile(tmp_path / "mau.zip", "w") as z:
        z.writestr("manifest.json", json.dumps(man))
    with pytest.raises(ValueError, match="unsafe"):
        portabilidade.ler_pacote(tmp_path / "mau.zip")


def test_backup_roda_e_rotaciona(instalacao):
    for _ in range(4):
        portabilidade.backup(manter=2)
    st = portabilidade.estado_backups()
    assert st["count"] == 2 and st["age_days"] == 0.0


def test_cli(instalacao, tmp_path, capsys):
    ns = SimpleNamespace
    assert portabilidade.cmd_export(ns(path=str(tmp_path / "p.zip"), with_vault=False)) == 0
    assert portabilidade.cmd_import(ns(path=str(tmp_path / "p.zip"), map=["sem-igual"], apply=False, vault="")) == 1
    assert portabilidade.cmd_import(ns(path=str(tmp_path / "p.zip"), map=None, apply=False, vault="")) == 0
    assert "dry run" in capsys.readouterr().out
    assert portabilidade.cmd_backup(ns(status=False, keep=3)) == 0
